from __future__ import annotations

import re
import threading
from collections import deque
from typing import List, Dict, Tuple, Set, Optional
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup  # pip install beautifulsoup4

from .base import BaseSourceParser
from ..models import ToolDescription, SourceInput, ToolParameter
from .openapi_parser import OpenAPISpecParser
from .postman_parser import PostmanCollectionParser
from .tools_json_parser import ToolsJSONParser

# --- Crawler limits (tune as needed) -------------------------------------- #

# Hard cap on how many pages to fetch per URL source in classic mode.
MAX_PAGES = 200

# Maximum crawl depth from the starting URL in classic mode.
MAX_DEPTH = 6

# Hard cap on how many endpoints to emit.
MAX_ENDPOINTS = 500

# Request timeout in seconds.
REQUEST_TIMEOUT = 15

# Headless interactive exploration limits
JS_MAX_CLICK_DEPTH = 2          # How many “generations” of clicks
JS_MAX_CLICKS_PER_PAGE = 4      # Max auto-clicks per page


class URLDocsParser(BaseSourceParser):
    """
    Documentation URL parser / crawler with smart headless fallback.

    Behaviour:

    1. Start from the given URL.
    2. Stage 1 (classic):
         - Crawl HTML pages on the same domain using requests + BeautifulSoup.
         - Extract endpoints from:
             * text (GET /..., curl -X ..., https://.../api/...)
         - If endpoints found -> return them.
         - If no endpoints but the first page looks like a SPA shell, move to Stage 2.
    3. Stage 2 (headless Playwright, if available):
         - Launch Chromium in headless mode in a separate thread (to avoid
           the "sync API inside asyncio loop" error).
         - Open the start URL.
         - Wait until network idle or timeout.
         - Collect:
             * Rendered HTML
             * JSON bodies from network responses
             * Network requests (method + URL)
         - Auto-click “interesting” links/buttons a few times (REST / API / Service /
           Directory, etc.) and collect more network traffic + HTML.
         - Extract endpoints from all collected text + network calls.
    4. If still no endpoints found, emit a single "raw_url_docs" tool with:
         - snippet of the initial HTML
         - a "crawler_log" in metadata explaining what was attempted.

    Output is a list of ToolDescription objects, same shape as the Postman/OpenAPI/SDK parsers,
    so JSON/CSV export and chat integration work the same.
    """

    TYPE_NAME = "url"

    def can_handle(
        self,
        *,
        raw_bytes: bytes | None,
        filename: str | None,
        source: SourceInput,
    ) -> bool:
        # Only handle when explicit source_type is "url" or missing
        if source.source_type and source.source_type.lower() != self.TYPE_NAME:
            return False
        return bool(source.url)

    # ------------------------------------------------------------------ #
    # Public parse
    # ------------------------------------------------------------------ #
    def parse(
        self,
        *,
        raw_bytes: bytes | None,
        filename: str | None,
        source: SourceInput,
    ) -> List[ToolDescription]:
        if not source.url:
            raise ValueError("URL is required for URLDocsParser.")

        start_url = str(source.url)
        crawler_log: List[str] = []

        # Stage 0: try to parse URL as a structured spec (OpenAPI/Postman/tools JSON)
        structured_tools = self._try_parse_structured_spec(start_url, crawler_log)
        if structured_tools:
            if structured_tools:
                structured_tools[0].metadata = structured_tools[0].metadata or {}
                structured_tools[0].metadata["crawler_log"] = crawler_log
            print("\n".join(crawler_log))
            return structured_tools

        # Stage 1: classic crawl
        crawler_log.append(f"Starting classic crawl from {start_url}")
        endpoints = self._crawl_basic(start_url, crawler_log=crawler_log)

        # If we found endpoints, return them.
        if endpoints:
            crawler_log.append(
                f"Classic crawl discovered {len(endpoints)} endpoint(s)."
            )
            tools: List[ToolDescription] = [
                self._endpoint_to_tool(ep, start_url) for ep in endpoints
            ]
            if tools:
                tools[0].metadata = tools[0].metadata or {}
                tools[0].metadata["crawler_log"] = crawler_log
            # Print log to backend console for debugging
            print("\n".join(crawler_log))
            return tools

        # No endpoints from classic. Decide if we should try JS.
        crawler_log.append(
            "Classic crawl found no endpoints. Checking if first page looks like SPA shell."
        )

        try:
            html0, ct0 = self._fetch_page_basic(start_url)
        except Exception as e:
            html0, ct0 = "", ""
            crawler_log.append(f"Error fetching start URL in basic mode: {e!r}")

        looks_spa = self._looks_like_spa_shell(html0) if html0 else False

        if looks_spa:
            crawler_log.append(
                "First page looks like a SPA/JS shell (short HTML or JS loader detected). "
                "Attempting headless browser mode with Playwright."
            )
            js_endpoints = self._crawl_js_interactive(start_url, crawler_log=crawler_log)

            if js_endpoints:
                crawler_log.append(
                    f"Headless Playwright crawl discovered {len(js_endpoints)} endpoint(s)."
                )
                tools = [self._endpoint_to_tool(ep, start_url) for ep in js_endpoints]
                if tools:
                    tools[0].metadata = tools[0].metadata or {}
                    tools[0].metadata["crawler_log"] = crawler_log
                print("\n".join(crawler_log))
                return tools
            else:
                crawler_log.append(
                    "Headless Playwright crawl did not reveal any endpoints."
                )
        else:
            crawler_log.append(
                "First page does not look like a SPA shell; skipping headless mode."
            )

        # Still nothing -> fallback tool with crawler_log for frontend to show.
        snippet = html0[:2000] if html0 else ""
        crawler_log.append("Falling back to raw_url_docs tool.")
        print("\n".join(crawler_log))

        fallback_tool = ToolDescription(
            name="raw_url_docs",
            description=(
                "Raw documentation page fetched from URL. "
                "Crawler could not confidently extract endpoints."
            ),
            metadata={
                "source": "url",
                "url": start_url,
                "snippet": snippet,
                "crawler_log": crawler_log,
            },
        )

        return [fallback_tool]

    # ------------------------------------------------------------------ #
    # Basic fetching helpers
    # ------------------------------------------------------------------ #
    def _fetch_page_basic(self, url: str) -> Tuple[str, str]:
        """
        Classic HTTP fetch using requests. Returns (html_text, content_type).
        Raises on HTTP/network errors.
        """
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        ct = resp.headers.get("content-type", "").lower()
        return resp.text, ct

    def _try_parse_structured_spec(
        self,
        start_url: str,
        crawler_log: List[str],
    ) -> Optional[List[ToolDescription]]:
        try:
            resp = requests.get(start_url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except Exception as e:
            crawler_log.append(f"Spec detection fetch failed: {e!r}")
            return None

        content = resp.content or b""
        if not content:
            return None

        ct = (resp.headers.get("content-type", "") or "").lower()
        parsed = urlparse(start_url)
        path = parsed.path or ""
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""

        filename_hint = ""
        if ext in {"json", "yaml", "yml"}:
            filename_hint = f"spec.{ext}"
        elif "json" in ct:
            filename_hint = "spec.json"
        elif "yaml" in ct or "yml" in ct:
            filename_hint = "spec.yaml"
        else:
            sniff = content[:200].decode(errors="ignore").lower()
            if "openapi" in sniff or "\"swagger\"" in sniff or "\"info\"" in sniff:
                filename_hint = "spec.json"

        if not filename_hint:
            return None

        crawler_log.append(
            f"Detected structured content at URL (content-type: {ct or 'unknown'}). "
            "Attempting OpenAPI/Postman/tools JSON parsing."
        )

        parsers = [
            ("openapi", OpenAPISpecParser()),
            ("postman", PostmanCollectionParser()),
            ("tools_json", ToolsJSONParser()),
        ]
        for parser_name, parser in parsers:
            try:
                tools = parser.parse(
                    raw_bytes=content,
                    filename=filename_hint,
                    source=SourceInput(source_type=parser_name, url=start_url),
                )
                if tools:
                    crawler_log.append(f"Parsed {len(tools)} tool(s) using {parser_name} parser.")
                    return tools
            except Exception as e:
                crawler_log.append(f"{parser_name} parser failed: {e!r}")

        return None

    # ------------------------------------------------------------------ #
    # Classic crawling (requests + BeautifulSoup)
    # ------------------------------------------------------------------ #
    def _crawl_basic(
        self,
        start_url: str,
        *,
        crawler_log: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """
        Classic crawl: requests + BeautifulSoup only (no JS).
        """
        log = crawler_log if crawler_log is not None else []
        parsed_start = urlparse(start_url)
        base_domain = parsed_start.netloc
        scheme = parsed_start.scheme or "https"
        base_root = f"{scheme}://{base_domain}"

        start_path = parsed_start.path or "/"
        start_prefix = start_path.rsplit("/", 1)[0] or "/"

        to_visit: deque[tuple[str, int]] = deque([(start_url, 0)])
        visited: Set[str] = set()
        endpoints: Dict[Tuple[str, str, str], Dict[str, str]] = {}
        pages_processed = 0

        while to_visit and pages_processed < MAX_PAGES:
            url, depth = to_visit.popleft()
            if url in visited:
                continue
            visited.add(url)

            try:
                html, content_type = self._fetch_page_basic(url)
            except Exception as e:
                log.append(f"[classic] Error fetching {url}: {e!r}")
                continue

            if "text/html" not in content_type:
                continue

            pages_processed += 1
            log.append(f"[classic] Visited {url} (depth={depth})")

            soup = BeautifulSoup(html, "html.parser")
            page_text = soup.get_text("\n", strip=True)
            code_texts = [
                el.get_text("\n", strip=True)
                for el in soup.find_all(["code", "pre"])
            ]
            combined_text = "\n".join(code_texts) + "\n" + page_text

            new_eps = self._extract_endpoints_from_text(
                combined_text,
                page_url=url,
                default_base_url=base_root,
            )
            if new_eps:
                log.append(
                    f"[classic] Found {len(new_eps)} endpoint(s) on {url}"
                )

            for key, ep in new_eps.items():
                endpoints.setdefault(key, ep)
                if len(endpoints) >= MAX_ENDPOINTS:
                    log.append(
                        f"[classic] Reached MAX_ENDPOINTS={MAX_ENDPOINTS}, stopping."
                    )
                    break

            if len(endpoints) >= MAX_ENDPOINTS:
                break

            if depth >= MAX_DEPTH:
                continue

            # Crawl links
            for a in soup.find_all("a", href=True):
                href = a["href"]
                next_url = urljoin(url, href)
                parsed_next = urlparse(next_url)

                if parsed_next.netloc != base_domain:
                    continue
                if parsed_next.scheme not in ("http", "https"):
                    continue

                if not parsed_next.path.startswith(start_prefix):
                    if not any(
                        tok in parsed_next.path.lower()
                        for tok in ("api", "rest", "services", "service", "graphql", "sdk", "ccx")
                    ):
                        continue

                if next_url not in visited:
                    to_visit.append((next_url, depth + 1))

        return list(endpoints.values())

    # ------------------------------------------------------------------ #
    # SPA detection
    # ------------------------------------------------------------------ #
    def _looks_like_spa_shell(self, html: str) -> bool:
        """
        Heuristic: decide if HTML looks like a SPA loader shell
        rather than fully rendered docs.
        """
        lower = (html or "").lower()
        text_len = len(html or "")

        # Very short HTML is suspicious for docs.
        if text_len < 2500:
            return True

        # Typical markers for SPA shells / loaders.
        if "you need to enable javascript to run this app" in lower:
            return True
        if 'id="root"' in lower or 'id="__next"' in lower:
            return True
        if "<meta http-equiv=\"refresh\"" in lower:
            return True

        return False

    # ------------------------------------------------------------------ #
    # JS interactive crawling (Playwright headless in a separate thread)
    # ------------------------------------------------------------------ #
    # ------------------------------------------------------------------ #
    # JS interactive crawling (Playwright headless in a separate thread)
    # ------------------------------------------------------------------ #
    def _crawl_js_interactive(
        self,
        start_url: str,
        *,
        crawler_log: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """
        Use Playwright (headless) to load the SPA, watch network traffic,
        auto-click a few interesting links/buttons, and extract endpoints
        from network calls and DOM/JSON.

        This is executed in a separate thread to avoid the
        "Playwright Sync API inside asyncio loop" error.
        """
        log = crawler_log if crawler_log is not None else []
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError  # type: ignore
        except Exception as e:
            log.append(
                f"[js] Playwright not available or import failed: {e!r}. "
                "Skipping headless mode."
            )
            return []

        parsed_start = urlparse(start_url)
        base_domain = parsed_start.netloc
        scheme = parsed_start.scheme or "https"
        base_root = f"{scheme}://{base_domain}"

        # We'll run the heavy part in a worker thread
        result_holder: Dict[str, List[Dict[str, str]]] = {"endpoints": []}
        error_holder: Dict[str, Optional[Exception]] = {"error": None}

        def worker():
            try:
                endpoints: Dict[Tuple[str, str, str], Dict[str, str]] = {}

                with sync_playwright() as p:
                    # NOTE: set headless=False temporarily if you want to SEE the browser
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()

                    json_blobs: List[str] = []
                    network_calls: List[Tuple[str, str]] = []

                    # Collect JSON responses
                    def handle_response(resp):
                        try:
                            ct = (resp.headers.get("content-type") or "").lower()
                        except Exception:
                            ct = ""
                        if "application/json" in ct or "text/json" in ct:
                            try:
                                body = resp.text()
                            except Exception:
                                try:
                                    body = resp.body().decode("utf-8", "ignore")
                                except Exception:
                                    body = ""
                            if body:
                                json_blobs.append(body)

                    # Collect network requests
                    def handle_request(req):
                        try:
                            method = req.method
                            full_url = req.url
                            network_calls.append((method, full_url))
                        except Exception:
                            pass

                    page.on("response", handle_response)
                    page.on("request", handle_request)

                    log.append(f"[js] Opening {start_url} in headless browser (wait_until='load')...")
                    try:
                        # More permissive than "networkidle"
                        page.goto(
                            start_url,
                            wait_until="load",
                            timeout=30000,  # 30s; tune if you like
                        )
                        # Short extra wait for lazy XHRs
                        page.wait_for_timeout(1500)
                        log.append("[js] Page load (load event) complete.")
                    except PlaywrightTimeoutError as te:
                        # Don't treat this as fatal; use whatever we have
                        log.append(
                            f"[js] Timeout during page.goto (load). "
                            f"Continuing with whatever content is available. Error: {te!r}"
                        )
                    except Exception as e:
                        # Real, unexpected error → bail out of JS mode
                        log.append(f"[js] Unexpected error in page.goto: {e!r}")
                        browser.close()
                        error_holder["error"] = e
                        return

                    # Auto-explore with clicks
                    self._auto_explore_page(
                        page,
                        base_root=base_root,
                        crawler_log=log,
                        current_depth=0,
                        max_depth=JS_MAX_CLICK_DEPTH,
                    )

                    # Final HTML after exploration (even if goto timed out)
                    html = page.content()
                    browser.close()

                combined_text = html + "\n\n" + "\n\n".join(json_blobs)
                log.append(
                    f"[js] Collected {len(network_calls)} network request(s) "
                    f"and {len(json_blobs)} JSON response(s)."
                )

                # From text (DOM + JSON)
                eps_text = self._extract_endpoints_from_text(
                    combined_text,
                    page_url=start_url,
                    default_base_url=base_root,
                )

                # From network calls
                eps_net = self._extract_endpoints_from_requests(
                    network_calls,
                    page_url=start_url,
                    default_base_url=base_root,
                )

                for key, ep in {**eps_text, **eps_net}.items():
                    endpoints.setdefault(key, ep)
                    if len(endpoints) >= MAX_ENDPOINTS:
                        log.append(
                            f"[js] Reached MAX_ENDPOINTS={MAX_ENDPOINTS}, stopping."
                        )
                        break

                result_holder["endpoints"] = list(endpoints.values())

            except Exception as e:
                error_holder["error"] = e

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join()

        if error_holder["error"] is not None:
            log.append(f"[js] Error during Playwright crawl (thread): {error_holder['error']!r}")
            return []

        return result_holder["endpoints"]

    def _auto_explore_page(
        self,
        page,
        *,
        base_root: str,
        crawler_log: List[str],
        current_depth: int,
        max_depth: int,
    ) -> None:
        """
        Heuristic auto-clicker for SPA pages.

        At each depth level:
          - Find <a> and <button> elements with "interesting" text.
          - Click up to JS_MAX_CLICKS_PER_PAGE of them, one by one.
          - After each click, wait briefly for network activity.
          - Recursively go deeper up to max_depth.
        """
        if current_depth >= max_depth:
            return

        try:
            elements = page.query_selector_all("a, button")
        except Exception as e:
            crawler_log.append(f"[js] Could not query links/buttons: {e!r}")
            return

        interesting_elements = []
        keywords = [
            "rest",
            "api",
            "service",
            "services",
            "directory",
            "reference",
            "detail",
            "details",
            "documentation",
        ]

        for el in elements:
            try:
                text = (el.inner_text() or "").strip()
            except Exception:
                text = ""
            if not text:
                continue
            score = sum(1 for kw in keywords if kw in text.lower())
            if score > 0:
                interesting_elements.append((score, text, el))

        # Sort by score desc, then by length of text
        interesting_elements.sort(key=lambda x: (-x[0], len(x[1])))

        to_click = interesting_elements[:JS_MAX_CLICKS_PER_PAGE]

        if not to_click:
            crawler_log.append(
                f"[js] No interesting clickable elements found at depth {current_depth}."
            )
            return

        crawler_log.append(
            f"[js] Found {len(interesting_elements)} interesting element(s), "
            f"clicking top {len(to_click)} at depth {current_depth}."
        )

        for score, text, el in to_click:
            try:
                crawler_log.append(f"[js] Clicking element (score={score}): {text!r}")
                el.click()
                # Wait a bit for any new network activity / DOM change
                page.wait_for_timeout(1500)
            except Exception as e:
                crawler_log.append(f"[js] Error clicking element {text!r}: {e!r}")
                continue

            # Recursive exploration from new state
            self._auto_explore_page(
                page,
                base_root=base_root,
                crawler_log=crawler_log,
                current_depth=current_depth + 1,
                max_depth=max_depth,
            )

    # ------------------------------------------------------------------ #
    # Endpoint extraction from TEXT
    # ------------------------------------------------------------------ #
    def _extract_endpoints_from_text(
        self,
        text: str,
        *,
        page_url: str,
        default_base_url: str,
    ) -> Dict[Tuple[str, str, str], Dict[str, str]]:
        """
        Extract candidate endpoints from arbitrary documentation text.

        Returns mapping:
            (method, path, base_url) -> endpoint dict
        """
        endpoints: Dict[Tuple[str, str, str], Dict[str, str]] = {}

        # Pattern 1: "GET /v1/users/{id}"
        method_path_pattern = re.compile(
            r"\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(/[\w\-./:{}]+)",
            re.IGNORECASE,
        )

        # Pattern 2: curl -X POST https://api.example.com/v1/foo?limit=10
        curl_pattern = re.compile(
            r"curl\s+-X\s+"
            r"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+"
            r"[\"']?(https?://[^\s\"']+)",
            re.IGNORECASE,
        )

        # Pattern 3: bare URLs that look like API endpoints
        bare_url_pattern = re.compile(
            r"(https?://[^\s\"']+/(?:api|services|service|rest|graphql|ccx)[^\s\"']*)",
            re.IGNORECASE,
        )

        # Pattern 4: REST resource paths (common in simple API homepages)
        # Matches: /posts, /users, /comments, /posts/:id, /users/{id}
        # Often found on simple REST API testing sites like JSONPlaceholder
        rest_resource_pattern = re.compile(
            r"(?:^|\s|['\"`])(/[\w\-]+(?:/(?:\{[\w\-]+\}|:[\w\-]+|[\w\-]+))*)(?:\s|['\"`]|$)",
            re.MULTILINE,
        )

        # --- Pattern 1: METHOD /path ---------------------------------- #
        for match in method_path_pattern.finditer(text):
            method = match.group(1).upper()
            path = match.group(2).strip()
            key = (method, path, default_base_url)
            snippet = text[max(0, match.start() - 80): match.end() + 80]
            endpoints[key] = {
                "method": method,
                "path": path,
                "base_url": default_base_url,
                "page_url": page_url,
                "example_snippet": snippet.strip(),
                "query_params": "",
                "body_keys": "",
            }

        # --- Pattern 2: curl -X METHOD FULL_URL ----------------------- #
        for match in curl_pattern.finditer(text):
            method = match.group(1).upper()
            full_url = match.group(2).strip()
            parsed = urlparse(full_url)
            if not parsed.scheme or not parsed.netloc:
                continue
            path = parsed.path or "/"
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            key = (method, path, base_url)
            snippet = text[max(0, match.start() - 120): match.end() + 120]

            query_params = self._extract_query_param_names(parsed.query)
            body_keys = self._extract_body_keys_around(text, match.end())

            endpoints.setdefault(
                key,
                {
                    "method": method,
                    "path": path,
                    "base_url": base_url,
                    "page_url": page_url,
                    "example_snippet": snippet.strip(),
                    "query_params": ",".join(sorted(query_params)),
                    "body_keys": ",".join(sorted(body_keys)),
                },
            )

        # --- Pattern 3: bare URLs (assume GET) ------------------------ #
        for match in bare_url_pattern.finditer(text):
            full_url = match.group(1).strip()
            parsed = urlparse(full_url)
            if not parsed.scheme or not parsed.netloc:
                continue
            path = parsed.path or "/"
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            method = "GET"
            key = (method, path, base_url)
            snippet = text[max(0, match.start() - 80): match.end() + 80]
            query_params = self._extract_query_param_names(parsed.query)

            endpoints.setdefault(
                key,
                {
                    "method": method,
                    "path": path,
                    "base_url": base_url,
                    "page_url": page_url,
                    "example_snippet": snippet.strip(),
                    "query_params": ",".join(sorted(query_params)),
                    "body_keys": "",
                },
            )

        # --- Pattern 4: REST resource paths (for simple API homepages) --- #
        # This helps with sites like JSONPlaceholder that list paths like:
        # /posts, /comments, /users, /posts/:id, etc.
        for match in rest_resource_pattern.finditer(text):
            path = match.group(1).strip()
            # Skip very short paths or non-resource paths
            if len(path) < 2 or path in ["/", "/api"]:
                continue
            # Skip common non-API paths
            if any(skip in path.lower() for skip in ["/css", "/js", "/img", "/static", "/assets", "/favicon"]):
                continue
            # Skip paths with file extensions
            if re.search(r"\.(html|css|js|png|jpg|svg|ico|json|xml)$", path, re.IGNORECASE):
                continue
            
            # For each REST path, create common CRUD operations
            snippet = text[max(0, match.start() - 80): match.end() + 80]
            
            # Check if path has ID parameter
            has_id = "{id}" in path or ":id" in path or re.search(r"/\{[\w\-]+\}$", path) or re.search(r"/:[\w\-]+$", path)
            
            # If it has ID, create GET/PUT/PATCH/DELETE
            # If no ID, create GET/POST
            methods_to_create = []
            if has_id:
                methods_to_create = ["GET", "PUT", "PATCH", "DELETE"]
            else:
                methods_to_create = ["GET", "POST"]
            
            for method in methods_to_create:
                key = (method, path, default_base_url)
                endpoints.setdefault(
                    key,
                    {
                        "method": method,
                        "path": path,
                        "base_url": default_base_url,
                        "page_url": page_url,
                        "example_snippet": snippet.strip(),
                        "query_params": "",
                        "body_keys": "",
                    },
                )

        return endpoints

    # ------------------------------------------------------------------ #
    # Endpoint extraction from NETWORK CALLS
    # ------------------------------------------------------------------ #
    def _extract_endpoints_from_requests(
        self,
        calls: List[Tuple[str, str]],
        *,
        page_url: str,
        default_base_url: str,
    ) -> Dict[Tuple[str, str, str], Dict[str, str]]:
        """
        Extract endpoints from Playwright network calls.

        calls: list of (method, full_url) captured by page.on("request", ...).

        Returns mapping:
            (method, path, base_url) -> endpoint dict
        """
        endpoints: Dict[Tuple[str, str, str], Dict[str, str]] = {}

        # Broader token set: covers common patterns + Workday-style /ccx/service/...
        interesting_tokens = (
            "api",
            "rest",
            "graphql",
            "services",
            "service",
            "ccx",
            "v1",
            "v2",
            "v3",
        )

        for method, full_url in calls:
            method = (method or "GET").upper()
            parsed = urlparse(full_url)
            if not parsed.scheme or not parsed.netloc:
                continue

            path = parsed.path or "/"
            base_url = f"{parsed.scheme}://{parsed.netloc}"

            # Only keep URLs that look API-ish.
            if not any(tok in path.lower() for tok in interesting_tokens):
                continue

            key = (method, path, base_url)
            query_params = self._extract_query_param_names(parsed.query)

            endpoints.setdefault(
                key,
                {
                    "method": method,
                    "path": path,
                    "base_url": base_url,
                    "page_url": page_url,
                    "example_snippet": f"Network request observed while loading {page_url}",
                    "query_params": ",".join(sorted(query_params)),
                    "body_keys": "",
                },
            )

        return endpoints

    # ------------------------------------------------------------------ #
    # Helpers for parameters
    # ------------------------------------------------------------------ #
    def _extract_query_param_names(self, query: str) -> List[str]:
        """
        Given a raw query string like "foo=1&bar={id}", return param names.
        """
        if not query:
            return []
        params = parse_qs(query, keep_blank_values=True)
        return list(params.keys())

    def _extract_body_keys_around(self, text: str, pos: int) -> List[str]:
        """
        Look near `pos` for a JSON-ish body in a curl example, then
        heuristically extract top-level keys.

        Example:
            curl ... -d '{"name": "foo", "limit": 10}'
        """
        window = text[pos: pos + 400]
        start = window.find("{")
        end = window.find("}")
        if start == -1 or end == -1 or end <= start:
            return []
        snippet = window[start: end + 1]

        key_pattern = re.compile(r'"([a-zA-Z_][a-zA-Z0-9_]*)"\s*:')
        keys = key_pattern.findall(snippet)
        return list(set(keys))

    # ------------------------------------------------------------------ #
    # Tool conversion
    # ------------------------------------------------------------------ #
    def _endpoint_to_tool(
        self,
        ep: Dict[str, str],
        start_url: str,
    ) -> ToolDescription:
        method = ep.get("method", "GET").upper()
        path = ep.get("path") or "/"
        base_url = ep.get("base_url") or ""
        page_url = ep.get("page_url") or start_url
        snippet = ep.get("example_snippet") or ""
        query_params = [p for p in (ep.get("query_params") or "").split(",") if p]
        body_keys = [p for p in (ep.get("body_keys") or "").split(",") if p]

        name = self._make_tool_name(method, path)

        parameters: List[ToolParameter] = []

        # Path params: {id} or :id
        path_param_names = set(re.findall(r"{([^}]+)}", path))
        path_param_names.update(
            re.findall(r":([a-zA-Z_][a-zA-Z0-9_]*)", path)
        )
        for p_name in sorted(path_param_names):
            parameters.append(
                ToolParameter(
                    name=p_name,
                    type="string",
                    required=True,
                    description=f"Path parameter inferred from URL: {p_name}.",
                )
            )

        # Query params (optional)
        for q in sorted(set(query_params)):
            if q in path_param_names:
                continue
            parameters.append(
                ToolParameter(
                    name=q,
                    type="string",
                    required=False,
                    description="Query parameter inferred from sample documentation URL or network call.",
                )
            )

        # Body params (optional)
        for b in sorted(set(body_keys)):
            if b in path_param_names or b in query_params:
                continue
            parameters.append(
                ToolParameter(
                    name=b,
                    type="string",
                    required=False,
                    description="Body field inferred from sample request payload.",
                )
            )

        desc = (
            f"HTTP {method} {path} discovered by crawling documentation pages "
            f"starting from {start_url}. Source page: {page_url}."
        )

        tags = ["url-scraped"]
        parsed_start = urlparse(start_url)
        if parsed_start.netloc:
            tags.append(parsed_start.netloc)

        return ToolDescription(
            name=name,
            description=desc,
            method=method,
            path=path,
            tags=tags,
            parameters=parameters,
            metadata={
                "source": "url",
                "start_url": start_url,
                "page_url": page_url,
                "base_url": base_url,
                "snippet": snippet[:1000],
            },
        )

    def _make_tool_name(self, method: str, path: str) -> str:
        """
        Generate a tool name like "get_services_data_v58_0_sobjects_id".
        """
        cleaned = path.strip("/")
        if not cleaned:
            cleaned = "root"
        cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", cleaned)
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        return f"{method.lower()}_{cleaned}" if cleaned else method.lower()

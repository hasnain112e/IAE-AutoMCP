# Edited by Dr. Wasim
# api_collector_backend/app.py
from __future__ import annotations

from typing import Optional, List

import io
import subprocess
import os
import tempfile
import json

from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    BackgroundTasks,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse

from .models import CollectToolsRequest, SourceInput, CollectToolsResponse
from .core.collector import APICollector
import uuid
import threading

# Load environment variables once at startup (before importing chat router)
load_dotenv()
from .chat_endpoint import router as chat_router
from .system_a_routes import router as system_a_router

app = FastAPI(
    title="API Collector Backend",
    description="Collect tools from Postman, OpenAPI, SDKs, or URL docs.",
    version="0.1.0",
)

# CORS for frontend (adjust origins in prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

collector = APICollector()  # Dependency-injected service

# Include chat router and System A wrapper
app.include_router(chat_router)
app.include_router(system_a_router)

# Background job tracking
job_status_dict = {}
job_lock = threading.Lock()

# Startup message
print("="*60)
print("🚀 API Collector Backend v2.0 - Background Jobs Enabled")
print("="*60)
print("✅ Features: Background job processing, status polling")
print("✅ Endpoints: /create-mcp-server, /job-status/{job_id}, /jobs, /health")
print("="*60)


# ---------------------------------------------------------------------------
# WebSocket progress streaming
# ---------------------------------------------------------------------------


class ProgressConnectionManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str) -> None:
        """Send a text message to all connected clients, dropping dead ones."""
        to_remove: List[WebSocket] = []
        for ws in self.active_connections:
            try:
                await ws.send_text(message)
            except Exception:
                to_remove.append(ws)
        for ws in to_remove:
            self.disconnect(ws)


progress_manager = ProgressConnectionManager()


@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    """
    Frontend connects here (ws://localhost:8000/ws/progress) to receive
    live progress messages. We don't require the client to send anything;
    we just keep the connection open until it disconnects.
    """
    await progress_manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive; we don't use incoming messages for now.
            await websocket.receive_text()
    except WebSocketDisconnect:
        progress_manager.disconnect(websocket)
    except Exception:
        progress_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.post("/collect-tools", response_model=CollectToolsResponse)
async def collect_tools_endpoint(
    # At least one of these is required:
    file: Optional[UploadFile] = File(default=None),
    url: Optional[str] = Form(default=None),
    sdk_name: Optional[str] = Form(default=None),
    source_type: Optional[str] = Form(
        default=None,
        description="Optional explicit type: postman | openapi | sdk | url",
    ),
    output_format: str = Form(default="json"),
    file_extension_hint: Optional[str] = Form(
        default=None,
        description="Optional file extension hint if filename is missing.",
    ),
):
    """
    Main entrypoint used by frontend.

    - If `file` is provided: try Postman/OpenAPI/etc.
    - Else if `sdk_name` is provided: introspect a Python SDK.
    - Else if `url` is provided: fetch docs URL / swagger / crawl.
    """
    if not any([file, url, sdk_name]):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: file, url, sdk_name",
        )

    await progress_manager.broadcast("▶️ Starting tool collection job…")
    if sdk_name:
        await progress_manager.broadcast("⏳ Installing SDK dependencies... please wait")
    await progress_manager.broadcast("▶️ Starting tool collection job…")
    if sdk_name:
        await progress_manager.broadcast("⏳ Installing SDK dependencies... please wait")

    # Read file if present
    raw_bytes = await file.read() if file is not None else None
    filename = file.filename if file is not None else None

    if file_extension_hint and not filename:
        filename = f"virtual.{file_extension_hint.lstrip('.')}"

    src = SourceInput(
        source_type=source_type,
        url=url,
        sdk_name=sdk_name,
    )

    req = CollectToolsRequest(
        source=src,
        output_format=output_format,
        file_extension_hint=file_extension_hint,
    )

    try:
        await progress_manager.broadcast("📦 Selecting appropriate parser for this source…")

        resp = collector.collect_tools(
            request=req,
            raw_bytes=raw_bytes,
            filename=filename,
        )

        await progress_manager.broadcast(f"🧰 Parsed {len(resp.tools)} tool(s) from source.")

        # If any tool has a crawler_log in metadata (e.g., URL crawler), stream it.
        for t in resp.tools:
            meta = getattr(t, "metadata", {}) or {}
            crawler_log = meta.get("crawler_log")
            if isinstance(crawler_log, list) and crawler_log:
                await progress_manager.broadcast("🌐 Crawler log:")
                for line in crawler_log:
                    await progress_manager.broadcast(f" • {line}")
                break  # only stream first crawler log found

        await progress_manager.broadcast("✅ Tool collection job finished.")

        # Auto-save to MongoDB (fail-silent — app works even if Mongo is down)
        try:
            from .mongo_store import save_tools
            source_name = filename or url or sdk_name or "unknown"
            saved_id = save_tools(
                source_type=resp.source_type,
                source_name=source_name,
                tools=resp.tools,
                output_format=resp.output_format,
            )
            await progress_manager.broadcast(f"💾 Saved to MongoDB (id: {saved_id[:8]}…)")
        except Exception as mongo_err:
            print(f"[mongo_store] save failed (non-critical): {mongo_err}")

        return resp

    except Exception as e:
        # 🔍 IMPORTANT: this prints the underlying cause into your backend logs
        print("collector.collect_tools error:", repr(e))
        await progress_manager.broadcast(f"❌ Error during tool collection: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/collect-tools/download")
async def collect_tools_download(
    file: Optional[UploadFile] = File(default=None),
    url: Optional[str] = Form(default=None),
    sdk_name: Optional[str] = Form(default=None),
    source_type: Optional[str] = Form(
        default=None,
        description="Optional explicit type: postman | openapi | sdk | url",
    ),
    output_format: str = Form(default="json"),
    file_extension_hint: Optional[str] = Form(
        default=None,
        description="Optional file extension hint if filename is missing.",
    ),
):
    """
    Same as /collect-tools but returns a downloadable CSV or JSON file.

    - output_format = "csv"  => tools.csv
    - output_format = "json" => tools.json (list of tools only)
    """
    if not any([file, url, sdk_name]):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: file, url, sdk_name",
        )

    raw_bytes = await file.read() if file is not None else None
    filename = file.filename if file is not None else None

    if file_extension_hint and not filename:
        filename = f"virtual.{file_extension_hint.lstrip('.')}"

    src = SourceInput(
        source_type=source_type,
        url=url,
        sdk_name=sdk_name,
    )

    req = CollectToolsRequest(
        source=src,
        output_format=output_format,
        file_extension_hint=file_extension_hint,
    )

    try:
        resp = collector.collect_tools(
            request=req,
            raw_bytes=raw_bytes,
            filename=filename,
        )
    except Exception as e:
        print("collector.collect_tools (download) error:", repr(e))
        raise HTTPException(status_code=400, detail=str(e))

    if output_format == "csv":
        if not resp.csv_content:
            raise HTTPException(status_code=500, detail="No CSV content generated")
        stream = io.StringIO(resp.csv_content)
        return StreamingResponse(
            stream,
            media_type="text/csv",
            headers={
                "Content-Disposition": 'attachment; filename="tools.csv"'
            },
        )
    else:
        # JSON: just dump the list of tools as an array
        tools_as_dicts = [t.model_dump() for t in resp.tools]
        return JSONResponse(
            content=tools_as_dicts,
            headers={
                "Content-Disposition": 'attachment; filename="tools.json"'
            },
        )


def run_mcp_generation_background(
    job_id: str,
    api_spec_path: str,
    output_file_path: str,
    api_spec_filename: str,
    api_spec_relative_path: str,
    project_root: str,
    script_path: str,
    incremental: bool,
    tools_per_batch: int,
    max_tools: int,
):
    """Background task to run MCP server generation."""
    print(f"🚀 Background task started for job {job_id[:8]}...")
    
    try:
        # Verify job exists in dict
        with job_lock:
            if job_id not in job_status_dict:
                print(f"❌ CRITICAL: Job {job_id} not in dict when background task started!")
                print(f"   Available jobs: {list(job_status_dict.keys())}")
                return
        
        # Update status to running
        with job_lock:
            job_status_dict[job_id]["status"] = "running"
            job_status_dict[job_id]["message"] = "Starting MCP server generation..."
        
        print(f"✅ Job {job_id[:8]}... status updated to 'running'")
        
        # Set environment variables for SSL
        env = os.environ.copy()
        env["PYTHONHTTPSVERIFY"] = "0"
        env["CURL_CA_BUNDLE"] = ""
        env["REQUESTS_CA_BUNDLE"] = ""
        env["SSL_VERIFY"] = "false"
        
        # Create Python command with SSL patches
        python_command_with_args = f"""
import ssl
import warnings
import sys
import os
warnings.filterwarnings('ignore', message='Unverified HTTPS request')
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['PYTHONHTTPSVERIFY'] = '0'

os.environ['API_SPEC_FILENAME'] = {repr(api_spec_relative_path)}

try:
    import httpx
    original_init = httpx.AsyncClient.__init__
    def patched_init(self, *args, **kwargs):
        kwargs['verify'] = False
        return original_init(self, *args, **kwargs)
    httpx.AsyncClient.__init__ = patched_init
    
    original_sync_init = httpx.Client.__init__
    def patched_sync_init(self, *args, **kwargs):
        kwargs['verify'] = False
        return original_sync_init(self, *args, **kwargs)
    httpx.Client.__init__ = patched_sync_init
except ImportError:
    pass

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    from urllib3.util import ssl_
    ssl_.DEFAULT_CIPHERS = 'ALL'
except ImportError:
    pass

sys.argv = ['agent_mcp_generator.py', {repr(api_spec_path)}, '--output', {repr(output_file_path)}]
sys.path.insert(0, {repr(project_root)})

# Set Windows event loop policy BEFORE importing modules (fixes asyncio issues on Windows)
import asyncio
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import importlib.util
spec = importlib.util.spec_from_file_location("agent_mcp_generator", {repr(script_path)})
module = importlib.util.module_from_spec(spec)
module.__name__ = "agent_mcp_generator"
spec.loader.exec_module(module)

# Use manual event loop management (more reliable in subprocess context)
# Create a new event loop explicitly with proper error handling
loop = None
try:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Run the async function
    output_path = loop.run_until_complete(module.generate_mcp_code(
        {repr(api_spec_path)}, 
        {repr(output_file_path)},
        incremental={incremental},
        tools_per_batch={tools_per_batch},
        max_tools={max_tools}
    ))
except Exception as e:
    # Print the full error for debugging - this will be captured in stderr
    import traceback
    error_details = traceback.format_exc()
    print("=" * 80, file=sys.stderr)
    print("ERROR in subprocess execution:", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    print(error_details, file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    # Also print to stdout so it's captured
    print("ERROR:", str(e))
    print(error_details)
    raise
finally:
    # Clean up the event loop
    if loop is not None:
        try:
            # Get all tasks
            try:
                pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                # Wait for cancellation to complete (with timeout)
                if pending:
                    loop.run_until_complete(asyncio.wait_for(
                        asyncio.gather(*pending, return_exceptions=True),
                        timeout=5.0
                    ))
            except (asyncio.TimeoutError, RuntimeError, Exception):
                # Ignore errors during cleanup
                pass
        except Exception:
            # Ignore all cleanup errors
            pass
        finally:
            try:
                loop.close()
            except Exception:
                pass
"""
        
        # Calculate timeout
        timeout_seconds = 7200  # 2 hours max for background tasks
        
        # Run the command
        result = subprocess.run(
            ["python", "-c", python_command_with_args],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env
        )
        
        # Check if file was created
        generated_file_path = os.path.join(project_root, "mcp-generator", "mcp_server_generated.py")
        file_created = os.path.exists(generated_file_path) and os.path.getsize(generated_file_path) > 0
        
        # Check for cleanup errors
        is_cleanup_error = (
            result.returncode != 0 and 
            ("KeyboardInterrupt" in result.stderr or "KeyboardInterrupt" in result.stdout) and
            ("shutdown_default_executor" in result.stderr or "shutdown_default_executor" in result.stdout)
        )
        
        if result.returncode == 0 or (file_created and is_cleanup_error):
            # Success - read the generated code
            try:
                with open(generated_file_path, 'r', encoding='utf-8') as f:
                    generated_code = f.read()
                
                # Post-process: Replace environment variable reference
                import re
                pattern = r"os\.environ\.get\(['\"]API_SPEC_FILENAME['\"](?:\s*,\s*['\"][^'\"]*['\"])?\)"
                generated_code = re.sub(pattern, repr(api_spec_filename), generated_code)
                
                with open(generated_file_path, 'w', encoding='utf-8') as f:
                    f.write(generated_code)
                
                # Save generated MCP server to MongoDB (fail-silent)
                mongo_id = None
                try:
                    from .mongo_store import save_mcp_server
                    with job_lock:
                        jd = job_status_dict.get(job_id, {})
                    mongo_id = save_mcp_server(
                        source_name=api_spec_filename,
                        source_type=jd.get("source_type", "unknown"),
                        generated_code=generated_code,
                        tools_count=jd.get("tools_count", 0),
                        api_spec_filename=api_spec_filename,
                    )
                    print(f"[mongo_store] MCP server saved to MongoDB: {mongo_id}")
                except Exception as mongo_err:
                    print(f"[mongo_store] MCP server save failed (non-critical): {mongo_err}")

                # Update job status to completed
                with job_lock:
                    job_status_dict[job_id]["status"] = "completed"
                    job_status_dict[job_id]["message"] = "MCP server generated successfully!"
                    job_status_dict[job_id]["result"] = {
                        "api_spec_path": api_spec_path,
                        "api_spec_relative_path": api_spec_relative_path,
                        "mcp_server_path": generated_file_path,
                        "mcp_server_relative_path": "mcp-generator/mcp_server_generated.py",
                        "generated_code": generated_code,
                        "mongo_id": mongo_id,
                    }
            except Exception as e:
                with job_lock:
                    job_status_dict[job_id]["status"] = "failed"
                    job_status_dict[job_id]["message"] = f"Error reading generated file: {str(e)}"
        else:
            # Failure - capture full error details
            error_msg = result.stderr if result.stderr else result.stdout
            if not error_msg:
                error_msg = "Unknown error occurred"
            
            # Try to extract the actual exception message
            error_lines = error_msg.split('\n')
            exception_line = None
            for i, line in enumerate(error_lines):
                if 'Traceback' in line or 'Error:' in line or 'Exception:' in line:
                    # Get the exception line and a few lines after it
                    exception_line = '\n'.join(error_lines[max(0, i-2):min(len(error_lines), i+15)])
                    break
            
            if exception_line:
                error_msg = exception_line
            
            # Limit error message length but try to keep important parts
            if len(error_msg) > 1500:
                # Keep first 750 and last 750 chars
                error_msg = error_msg[:750] + "\n... (truncated) ...\n" + error_msg[-750:]
            
            with job_lock:
                job_status_dict[job_id]["status"] = "failed"
                job_status_dict[job_id]["message"] = f"Script execution failed: {error_msg}"
    
    except subprocess.TimeoutExpired:
        with job_lock:
            job_status_dict[job_id]["status"] = "failed"
            job_status_dict[job_id]["message"] = "Script execution timed out"
    except Exception as e:
        with job_lock:
            job_status_dict[job_id]["status"] = "failed"
            job_status_dict[job_id]["message"] = f"Error: {str(e)}"


@app.post("/create-mcp-server")
async def create_mcp_server(
    background_tasks: BackgroundTasks,
    # At least one of these is required:
    file: Optional[UploadFile] = File(default=None),
    url: Optional[str] = Form(default=None),
    sdk_name: Optional[str] = Form(default=None),
    source_type: Optional[str] = Form(
        default=None,
        description="Optional explicit type: postman | openapi | sdk | url",
    ),
    output_format: str = Form(default="json"),
    file_extension_hint: Optional[str] = Form(
        default=None,
        description="Optional file extension hint if filename is missing.",
    ),
    incremental: bool = Form(
        default=True,
        description="Process tools incrementally (one at a time). Recommended for large specs.",
    ),
    tools_per_batch: int = Form(
        default=10,
        description="Number of tools to generate per batch when incremental=True (default: 10)",
    ),
    max_tools: int = Form(
        default=0,
        description="Maximum number of tools to process (0 = all tools). Use this to process large specs in chunks.",
    ),
):
    """
    Generate MCP server from user's API source (file/URL/SDK).
    First collects tools from the source, then generates MCP server code.
    """
    if not any([file, url, sdk_name]):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: file, url, sdk_name",
        )

    try:
        # Step 1: Generate JSON from user's source (same logic as collect-tools)
        raw_bytes = await file.read() if file is not None else None
        filename = file.filename if file is not None else None

        if file_extension_hint and not filename:
            filename = f"virtual.{file_extension_hint.lstrip('.')}"

        src = SourceInput(
            source_type=source_type,
            url=url,
            sdk_name=sdk_name,
        )

        req = CollectToolsRequest(
            source=src,
            output_format="json",  # Always use JSON for MCP generation
            file_extension_hint=file_extension_hint,
        )

        # Generate tools from user's source
        resp = collector.collect_tools(
            request=req,
            raw_bytes=raw_bytes,
            filename=filename,
        )

        # Step 2: Save tools to persistent JSON file (don't use temp file)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        
        # Create a meaningful filename based on source
        if file and file.filename:
            base_name = os.path.splitext(file.filename)[0]
        elif url:
            # Extract domain from URL
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                base_name = parsed.hostname.replace('.', '_') if parsed.hostname else 'url_api'
            except:
                base_name = 'url_api'
        elif sdk_name:
            base_name = sdk_name.replace('-', '_').replace('.', '_')
        else:
            base_name = 'api_spec'
        
        # Save to mcp-generator directory with a meaningful name
        api_spec_filename = f"{base_name}_spec.json"
        mcp_generator_dir = os.path.join(project_root, "mcp-generator")
        api_spec_path = os.path.join(mcp_generator_dir, api_spec_filename)
        
        with open(api_spec_path, 'w', encoding='utf-8') as spec_file:
            # Convert tools to JSON format expected by agent_mcp_generator
            tools_data = [tool.model_dump() for tool in resp.tools]
            json.dump(tools_data, spec_file, indent=2)

        # Step 3: Create background job for MCP generation
        job_id = str(uuid.uuid4())
        
        script_path = os.path.join(project_root, "mcp-generator", "agent_mcp_generator.py")
        # Use absolute path to avoid path joining issues
        output_file_path = os.path.join(project_root, "mcp-generator", "mcp_server_generated.py")
        api_spec_relative_path = api_spec_filename.replace('\\', '/')
        
        # Initialize job status FIRST (before any other operations)
        with job_lock:
            job_status_dict[job_id] = {
                "status": "queued",
                "message": "Job queued for processing",
                "result": None,
                "tools_count": len(resp.tools),
                "source_type": resp.source_type,
                "created_at": str(uuid.uuid4())[:8],  # For debugging
            }
        
        print(f"✅ Created job {job_id} - Tools: {len(resp.tools)}, Type: {resp.source_type}")
        print(f"   Total active jobs: {len(job_status_dict)}")
        
        # Start background task
        background_tasks.add_task(
            run_mcp_generation_background,
            job_id=job_id,
            api_spec_path=api_spec_path,
            output_file_path=output_file_path,
            api_spec_filename=api_spec_filename,
            api_spec_relative_path=api_spec_relative_path,
            project_root=project_root,
            script_path=script_path,
            incremental=incremental,
            tools_per_batch=tools_per_batch,
            max_tools=max_tools,
        )
        
        # Verify job was stored before returning
        with job_lock:
            if job_id not in job_status_dict:
                print(f"❌ ERROR: Job {job_id} not in dict before return!")
                raise HTTPException(status_code=500, detail="Failed to initialize job")
        
        print(f"✅ Returning job {job_id[:8]}... to client")
        
        # Return job ID immediately
        return {
            "success": True,
            "message": "MCP server generation started in background",
            "job_id": job_id,
            "tools_count": len(resp.tools),
            "source_type": resp.source_type,
            "api_spec_file": api_spec_filename,
            "api_spec_relative_path": api_spec_relative_path,
        }
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error starting MCP generator: {str(e)}"
        )


@app.get("/job-status/{job_id}")
async def get_job_status(job_id: str):
    """Get the status of a background MCP generation job."""
    with job_lock:
        if job_id not in job_status_dict:
            # Log for debugging
            available_jobs = list(job_status_dict.keys())
            print(f"❌ Job {job_id} not found!")
            print(f"   Available jobs ({len(available_jobs)}): {available_jobs[:5]}")  # Show first 5
            print(f"   This likely means the backend was restarted after job creation.")
            raise HTTPException(
                status_code=404, 
                detail=f"Job not found. Backend may have been restarted (jobs are stored in-memory). Active jobs: {len(available_jobs)}"
            )
        
        # Log successful status check
        job_data = job_status_dict[job_id]
        print(f"📊 Job {job_id[:8]}... - Status: {job_data.get('status')} - {job_data.get('message')}")
        return job_data


@app.get("/jobs")
async def list_jobs():
    """List all active jobs (for debugging)."""
    with job_lock:
        return {
            "total_jobs": len(job_status_dict),
            "jobs": [
                {
                    "job_id": job_id,
                    "status": job_data.get("status"),
                    "message": job_data.get("message"),
                }
                for job_id, job_data in job_status_dict.items()
            ]
        }


@app.get("/tools/history")
async def tools_history(limit: int = 50):
    """List all saved MCP tool collections (newest first)."""
    try:
        from .mongo_store import list_collections
        return {"success": True, "collections": list_collections(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {e}")


@app.get("/tools/{collection_id}")
async def get_tool_collection(collection_id: str):
    """Fetch a full saved tool collection by ID."""
    try:
        from .mongo_store import get_collection
        doc = get_collection(collection_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Collection not found")
        return {"success": True, "collection": doc}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {e}")


@app.delete("/tools/{collection_id}")
async def delete_tool_collection(collection_id: str):
    """Delete a saved tool collection by ID."""
    try:
        from .mongo_store import delete_collection
        deleted = delete_collection(collection_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Collection not found")
        return {"success": True, "deleted_id": collection_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {e}")


from pydantic import BaseModel as _PydanticBase

class DBMCPRequest(_PydanticBase):
    uri: str
    dbname: str = "admin"

class DBAgentConnectRequest(_PydanticBase):
    uri: str
    dbname: str = "admin"

class DBAgentQueryRequest(_PydanticBase):
    session_id: str
    question: str


@app.post("/generate-db-mcp")
async def generate_db_mcp(req: DBMCPRequest):
    """
    Input : MongoDB connection details (uri + dbname)
    Output: Generated MCP server code saved to MongoDB + returned to caller
    """
    from .db_mcp_generator import connect_and_get_schema, generate_mcp_code
    from .mongo_store import save_mcp_server

    # Step 1 — connect and discover schema
    try:
        schema = connect_and_get_schema(req.uri, req.dbname)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"DB connection failed: {e}")

    if not schema:
        raise HTTPException(status_code=400, detail="No collections found in database.")

    # Step 2 — generate MCP server code deterministically
    try:
        code = generate_mcp_code(req.uri, req.dbname, schema)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Code generation failed: {e}")

    # Step 3 — save to MongoDB
    tools_count = len(schema) * 2 + 3   # query_ + count_ per collection + 3 shared
    try:
        mongo_id = save_mcp_server(
            source_name=f"{req.dbname}@mongodb",
            source_type="mongodb",
            generated_code=code,
            tools_count=tools_count,
            api_spec_filename=req.uri,
        )
    except Exception as e:
        mongo_id = None

    return {
        "success": True,
        "dbname": req.dbname,
        "uri": req.uri,
        "collections": list(schema.keys()),
        "tools_count": tools_count,
        "mongo_id": mongo_id,
        "generated_code": code,
    }


@app.post("/db-agent/connect")
async def db_agent_connect(req: DBAgentConnectRequest):
    """Connect to user's MongoDB, discover schema, return session_id + collections."""
    from .db_agent import create_session
    try:
        result = create_session(req.uri, req.dbname)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {e}")


@app.post("/db-agent/query")
async def db_agent_query(req: DBAgentQueryRequest):
    """Answer a natural language question using the connected database."""
    from .db_agent import answer_question
    result = answer_question(req.session_id, req.question)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"success": True, **result}


@app.get("/mcp-servers")
async def list_mcp_servers(limit: int = 50):
    """List all stored MCP servers in MongoDB (newest first)."""
    try:
        from .mongo_store import list_mcp_servers
        return {"success": True, "servers": list_mcp_servers(limit=limit)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {e}")


@app.get("/mcp-servers/{server_id}")
async def get_mcp_server(server_id: str):
    """Fetch a full stored MCP server by ID (includes generated_code)."""
    try:
        from .mongo_store import get_mcp_server
        doc = get_mcp_server(server_id)
        if not doc:
            raise HTTPException(status_code=404, detail="MCP server not found")
        return {"success": True, "server": doc}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {e}")


@app.delete("/mcp-servers/{server_id}")
async def delete_mcp_server(server_id: str):
    """Delete a stored MCP server by ID."""
    try:
        from .mongo_store import delete_mcp_server
        deleted = delete_mcp_server(server_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="MCP server not found")
        return {"success": True, "deleted_id": server_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"MongoDB unavailable: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint with version info."""
    return {
        "status": "healthy",
        "version": "2.0-background-jobs",
        "features": ["background_jobs", "job_status_polling"],
        "active_jobs": len(job_status_dict)
    }


@app.get("/ready")
async def ready_check():
    """Ready check endpoint for frontend connection monitoring."""
    return {
        "backend": "ready",
        "status": "healthy",
        "version": "2.0-background-jobs"
    }

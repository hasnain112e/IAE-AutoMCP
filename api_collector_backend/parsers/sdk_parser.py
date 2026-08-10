# api_collector_backend/parsers/sdk_parser.py
from __future__ import annotations

from typing import List
import inspect
import importlib
import subprocess
import sys
import time

from .base import BaseSourceParser
from ..models import ToolDescription, ToolParameter, SourceInput


class PythonSDKParser(BaseSourceParser):
    TYPE_NAME = "sdk"

    def _is_user_cancelled(self, *, returncode: int, combined_output: str) -> bool:
        # Common user-cancel signals: Ctrl+C (130), KeyboardInterrupt in output.
        if returncode == 130:
            return True
        lowered = combined_output.lower()
        return "keyboardinterrupt" in lowered or "ctrl+c" in lowered

    def _is_system_termination(self, *, returncode: int, combined_output: str) -> bool:
        # Windows Ctrl+C / termination (0xC000013A) can be raised by the system too.
        if returncode == 3221225786:
            return True
        lowered = combined_output.lower()
        return "operation cancelled by user" in lowered and "keyboardinterrupt" not in lowered

    def _run_pip_install(self, sdk_name: str, *, timeout_seconds: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                sdk_name,
                "--disable-pip-version-check",
                "--no-input",
                "--no-cache-dir",
                "--retries",
                "3",
                "--timeout",
                "60",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

    def _pip_install_with_retries(
        self,
        sdk_name: str,
        *,
        max_attempts: int = 3,
        timeout_seconds: int = 300,
    ) -> None:
        last_error: str | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                result = self._run_pip_install(sdk_name, timeout_seconds=timeout_seconds)
            except subprocess.TimeoutExpired as e:
                last_error = f"System Timeout: pip install exceeded {timeout_seconds}s"
                if attempt < max_attempts:
                    time.sleep(2 * attempt)
                    continue
                raise ValueError(
                    f"Failed to install SDK '{sdk_name}': {last_error}"
                ) from e

            if result.returncode == 0:
                return

            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            combined = stderr or stdout or f"pip exited with code {result.returncode}"
            last_error = combined

            timeout_hint = combined.lower()
            is_timeout = "timeout" in timeout_hint or "timed out" in timeout_hint or "readtimeout" in timeout_hint
            if is_timeout and attempt < max_attempts:
                time.sleep(2 * attempt)
                continue
            if is_timeout:
                raise ValueError(
                    f"System Timeout: pip install exceeded {timeout_seconds}s"
                )

            if self._is_user_cancelled(returncode=result.returncode, combined_output=combined):
                raise ValueError(
                    "User Cancellation: pip install was cancelled by the user"
                )

            if self._is_system_termination(returncode=result.returncode, combined_output=combined):
                if attempt < max_attempts:
                    time.sleep(2 * attempt)
                    continue
                raise ValueError(
                    "System Termination: pip install was terminated by the system"
                )

            raise ValueError(
                f"Failed to install SDK '{sdk_name}': {combined}"
            )
        if last_error:
            raise ValueError(
                f"Failed to install SDK '{sdk_name}': {last_error}"
            )

    def can_handle(
        self,
        *,
        raw_bytes: bytes | None,
        filename: str | None,
        source: SourceInput,
    ) -> bool:
        """
        This parser is used whenever sdk_name is provided (and optional source_type is 'sdk').
        """
        if source.source_type and source.source_type.lower() != self.TYPE_NAME:
            return False
        return bool(source.sdk_name)

    def _import_sdk(self, sdk_name: str):
        """
        Import the SDK module; if missing, try to pip install it and import again.
        """
        try:
            return importlib.import_module(sdk_name)
        except ModuleNotFoundError:
            # WARNING: installs arbitrary packages; only enable this on trusted environments.
            try:
                self._pip_install_with_retries(sdk_name)
            except ValueError as e:
                raise ValueError(str(e)) from e

            # Try to import again after installation
            try:
                return importlib.import_module(sdk_name)
            except Exception as e:
                raise ValueError(
                    f"SDK '{sdk_name}' could not be imported even after install: {e}"
                ) from e

    def parse(
        self,
        *,
        raw_bytes: bytes | None,
        filename: str | None,
        source: SourceInput,
    ) -> List[ToolDescription]:
        if not source.sdk_name:
            raise ValueError("sdk_name is required for SDK parser.")

        module = self._import_sdk(source.sdk_name)
        tools: List[ToolDescription] = []

        for name, obj in inspect.getmembers(module, inspect.isfunction):
            # Skip private / dunder functions
            if name.startswith("_"):
                continue

            sig = inspect.signature(obj)
            params: List[ToolParameter] = []
            for pname, param in sig.parameters.items():
                if pname in {"self", "cls"}:
                    continue
                if param.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
                    continue

                ptype = "string"
                if param.annotation in (int, "int"):
                    ptype = "integer"
                elif param.annotation in (float, "float"):
                    ptype = "number"
                elif param.annotation in (bool, "bool"):
                    ptype = "boolean"

                params.append(
                    ToolParameter(
                        name=pname,
                        type=ptype,
                        required=param.default is inspect._empty,
                        default=None
                        if param.default is inspect._empty
                        else str(param.default),
                    )
                )

            doc = (inspect.getdoc(obj) or "").strip()
            description = doc.split("\n\n", 1)[0] if doc else f"SDK function {name}"

            tools.append(
                ToolDescription(
                    name=self._normalize_name(f"{source.sdk_name}_{name}"),
                    description=description,
                    method=None,
                    path=None,
                    tags=[source.sdk_name],
                    parameters=params,
                    metadata={
                        "source": "python_sdk",
                        "sdk_module": source.sdk_name,
                        "sdk_function": name,
                    },
                )
            )

        return tools

    def _normalize_name(self, name: str) -> str:
        sanitized = "".join(
            ch if ch.isalnum() else "_" for ch in name.lower()
        ).strip("_")
        if sanitized and sanitized[0].isdigit():
            sanitized = "e_" + sanitized
        return sanitized[:64]

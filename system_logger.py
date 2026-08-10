#!/usr/bin/env python3
"""
Centralized System Logger
Tracks all backend activities across all services
"""
import os
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import threading

class SystemLogger:
    """Centralized logging system for all backend activities"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # Create log file with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"system_{timestamp}.log"
        self.json_log_file = self.log_dir / f"system_{timestamp}.jsonl"
        
        # Setup logging
        self.logger = logging.getLogger("SystemLogger")
        self.logger.setLevel(logging.DEBUG)
        
        # File handler
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        
        # Thread lock for JSON logging
        self._lock = threading.Lock()
        
        self.log("SYSTEM", "System logger initialized", {"log_file": str(self.log_file)})
    
    def log(self, component: str, message: str, data: Optional[Dict[str, Any]] = None):
        """Log a message with component and optional data"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "component": component,
            "message": message,
            "data": data or {}
        }
        
        # Write to JSON log file
        with self._lock:
            with open(self.json_log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        
        # Write to standard log
        log_msg = f"[{component}] {message}"
        if data:
            log_msg += f" | Data: {json.dumps(data, ensure_ascii=False)}"
        
        self.logger.info(log_msg)
    
    def log_service_start(self, service_name: str, port: int, url: str):
        """Log service startup"""
        self.log(service_name, f"Service started on port {port}", {
            "port": port,
            "url": url,
            "status": "started"
        })
    
    def log_service_stop(self, service_name: str):
        """Log service shutdown"""
        self.log(service_name, "Service stopped", {"status": "stopped"})
    
    def log_validation(self, code_length: int, approved: bool, quality_score: Optional[float] = None):
        """Log validation event"""
        self.log("VALIDATOR", "Code validation completed", {
            "code_length": code_length,
            "approved": approved,
            "quality_score": quality_score
        })
    
    def log_mcp_generation(self, api_spec: str, output_file: str, success: bool):
        """Log MCP generation event"""
        self.log("CREATOR", "MCP code generation", {
            "api_spec": api_spec,
            "output_file": output_file,
            "success": success
        })
    
    def log_api_request(self, endpoint: str, method: str, status_code: int, duration_ms: float):
        """Log API request"""
        self.log("API", f"{method} {endpoint}", {
            "endpoint": endpoint,
            "method": method,
            "status_code": status_code,
            "duration_ms": duration_ms
        })
    
    def log_llm_call(self, provider: str, model: str, prompt_length: int, response_length: int, duration_ms: float):
        """Log LLM API call"""
        self.log("LLM", f"LLM call to {provider}/{model}", {
            "provider": provider,
            "model": model,
            "prompt_length": prompt_length,
            "response_length": response_length,
            "duration_ms": duration_ms
        })
    
    def log_error(self, component: str, error: Exception, context: Optional[Dict[str, Any]] = None):
        """Log error"""
        self.log(component, f"ERROR: {str(error)}", {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context or {}
        })
        self.logger.error(f"[{component}] {error}", exc_info=True)
    
    def get_recent_logs(self, component: Optional[str] = None, limit: int = 100) -> list:
        """Get recent log entries"""
        logs = []
        try:
            with open(self.json_log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        log_entry = json.loads(line)
                        if component is None or log_entry.get("component") == component:
                            logs.append(log_entry)
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            pass
        
        return logs[-limit:]
    
    def get_log_file_path(self) -> str:
        """Get path to log file"""
        return str(self.log_file)
    
    def get_json_log_file_path(self) -> str:
        """Get path to JSON log file"""
        return str(self.json_log_file)

# Global logger instance
_system_logger: Optional[SystemLogger] = None

def get_logger() -> SystemLogger:
    """Get global system logger instance"""
    global _system_logger
    if _system_logger is None:
        _system_logger = SystemLogger()
    return _system_logger


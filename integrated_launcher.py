#!/usr/bin/env python3
"""
Integrated System Launcher
Automatically starts all services and provides single entry point
"""
import os
import sys
import time
import subprocess
import threading
import signal
from pathlib import Path
from typing import List, Optional

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.absolute()))

try:
    import requests
except ImportError:
    print("ERROR: requests module not found. Install with: pip install requests")
    sys.exit(1)

try:
    from system_logger import get_logger
except ImportError as e:
    print(f"ERROR: Could not import system_logger: {e}")
    print("Make sure system_logger.py is in the same directory as integrated_launcher.py")
    sys.exit(1)

class ServiceManager:
    """Manages all system services"""
    
    def __init__(self):
        try:
            self.logger = get_logger()
        except Exception as e:
            print(f"WARNING: Could not initialize logger: {e}")
            # Create a simple logger fallback
            import logging
            logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
            self.logger = logging.getLogger("ServiceManager")
            # Add a dummy log method if needed
            if not hasattr(self.logger, 'log'):
                def log_method(component, message, data=None):
                    print(f"[{component}] {message}")
                self.logger.log = log_method
                self.logger.log_service_start = lambda name, port, url: print(f"[{name}] Service started on port {port}")
                self.logger.log_error = lambda component, error, context=None: print(f"[{component}] ERROR: {error}")
        
        self.processes: List[subprocess.Popen] = []
        self.services = {
            "validator": {
                "command": ["python", "IAE-AutoMCP-Mcp_super_Validator/http_server.py", "--port", "8002"],
                "port": 8002,
                "url": "http://localhost:8002",
                "health_endpoint": "/health",
                "started": False
            },
            "backend": {
                "command": ["uvicorn", "api_collector_backend.app:app", "--reload", "--port", "8000", "--host", "0.0.0.0"],
                "port": 8000,
                "url": "http://localhost:8000",
                "health_endpoint": "/docs",  # FastAPI docs endpoint as health check
                "started": False
            },
            "frontend": {
                "command": ["npm", "run", "dev"],
                "cwd": "api_collector_frontend",
                "port": 5173,
                "url": "http://localhost:5173",
                "health_endpoint": None,
                "started": False
            }
        }
    
    def start_service(self, service_name: str) -> bool:
        """Start a service"""
        if service_name not in self.services:
            self.logger.log_error("LAUNCHER", ValueError(f"Unknown service: {service_name}"))
            return False
        
        service = self.services[service_name]
        
        if service["started"]:
            self.logger.log(service_name, "Service already running")
            return True
        
        try:
            self.logger.log("LAUNCHER", f"Starting {service_name}...", {
                "command": " ".join(service["command"]),
                "port": service["port"]
            })
            
            # Set working directory
            project_root = Path(__file__).parent.absolute()
            cwd = project_root / service.get("cwd", "") if "cwd" in service else project_root

            # Set environment variables
            env = os.environ.copy()
            env['PYTHONPATH'] = str(project_root)
            
            process = subprocess.Popen(
                service["command"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=str(cwd),
                env=env,
                shell=True if sys.platform == "win32" else False
            )
            
            self.processes.append(process)
            service["started"] = True

            # Wait for service to be ready by reading its output
            ready = False
            for line in iter(process.stdout.readline, ''):
                print(f"[{service_name}] {line.strip()}")
                if "Uvicorn running on" in line or "vite v" in line or "Network URL" in line:
                    ready = True
                    break
            
            if not ready:
                stderr = process.stderr.read()
                self.logger.log_error("LAUNCHER", f"Service {service_name} failed to start.", {"stderr": stderr})
                return False

            self.logger.log_service_start(service_name, service["port"], service["url"])
            return True
                
        except Exception as e:
            self.logger.log_error("LAUNCHER", e, {"service": service_name})
            return False
    
    def check_service_health(self, service_name: str, timeout: int = 10) -> bool:
        """Check if service is healthy"""
        service = self.services[service_name]
        
        if service["health_endpoint"] is None:
            # For services without health endpoint, just check if port is open
            return self.check_port_open(service["port"], timeout)
        
        try:
            url = service["url"] + service["health_endpoint"]
            response = requests.get(url, timeout=timeout)
            return response.status_code == 200
        except Exception:
            return False
    
    def check_port_open(self, port: int, timeout: int = 5) -> bool:
        """Check if port is open"""
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex(('localhost', port))
        sock.close()
        return result == 0
    
    def start_all(self):
        """Start all services"""
        self.logger.log("LAUNCHER", "Starting all services...")
        
        # Start services in order
        services_order = ["validator", "backend", "frontend"]
        
        for service_name in services_order:
            if not self.start_service(service_name):
                self.logger.log("LAUNCHER", f"Failed to start {service_name}, continuing...")
        
        # Wait a bit for all services to stabilize
        time.sleep(5)
        
        # Print status
        self.print_status()
    
    def print_status(self):
        """Print status of all services"""
        print("\n" + "="*60)
        print("SYSTEM STATUS")
        print("="*60)
        
        for service_name, service in self.services.items():
            status = "✓ RUNNING" if service["started"] else "✗ STOPPED"
            print(f"{service_name.upper():15} | {status:12} | {service['url']}")
        
        print("="*60)
        print(f"\nMain Interface: {self.services['frontend']['url']}")
        print(f"Log File: {self.logger.get_log_file_path()}")
        print("\nPress Ctrl+C to stop all services\n")
    
    def stop_all(self):
        """Stop all services"""
        self.logger.log("LAUNCHER", "Stopping all services...")
        
        for process in self.processes:
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            except Exception as e:
                self.logger.log_error("LAUNCHER", e)
        
        for service_name in self.services:
            self.services[service_name]["started"] = False
        
        self.logger.log("LAUNCHER", "All services stopped")
    
    def wait(self):
        """Wait for services to run"""
        try:
            while True:
                time.sleep(1)
                # Check if any process died
                for i, process in enumerate(self.processes):
                    if process.poll() is not None:
                        self.logger.log("LAUNCHER", f"Process {i} exited with code {process.returncode}")
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.stop_all()

def main():
    """Main entry point"""
    try:
        print("Initializing Service Manager...")
        manager = ServiceManager()
        
        # Setup signal handlers
        def signal_handler(sig, frame):
            print("\nReceived shutdown signal...")
            manager.stop_all()
            sys.exit(0)
        
        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        except AttributeError:
            # Windows doesn't support SIGTERM
            pass
        
        # Start all services
        print("Starting all services...")
        manager.start_all()
        
        # Wait
        print("All services started. Waiting...")
        manager.wait()
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        if 'manager' in locals():
            manager.stop_all()
        sys.exit(0)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()


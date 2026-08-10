#!/usr/bin/env python3
"""
Entry point for running the API Collector Backend as a module.

Usage:
    python -m api_collector_backend
    or
    uvicorn api_collector_backend.app:app --reload --port 8000
"""
import uvicorn

if __name__ == "__main__":
    import os
    
    # Only watch the backend code directory, not the entire project
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    uvicorn.run(
        "api_collector_backend.app:app", 
        host="127.0.0.1", 
        port=8000, 
        reload=True,
        reload_dirs=[current_dir],  # Only watch api_collector_backend directory
    )


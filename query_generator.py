#!/usr/bin/env python3
"""
Query Generator
Generates sample LLM queries based on API specifications
"""
import json
from typing import List, Dict, Any
from system_logger import get_logger

class QueryGenerator:
    """Generates sample queries for LLM based on API specs"""
    
    def __init__(self):
        self.logger = get_logger()
    
    def generate_queries_from_json(self, json_file_path: str) -> List[str]:
        """Generate sample queries from JSON API spec file"""
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                api_spec = json.load(f)
            
            queries = []
            
            # Group endpoints by method
            get_endpoints = []
            post_endpoints = []
            put_endpoints = []
            delete_endpoints = []
            
            for tool in api_spec:
                method = tool.get("method", "").upper()
                name = tool.get("name", "")
                description = tool.get("description", "")
                path = tool.get("path", "")
                
                if method == "GET":
                    get_endpoints.append({"name": name, "path": path, "description": description})
                elif method == "POST":
                    post_endpoints.append({"name": name, "path": path, "description": description})
                elif method == "PUT":
                    put_endpoints.append({"name": name, "path": path, "description": description})
                elif method == "DELETE":
                    delete_endpoints.append({"name": name, "path": path, "description": description})
            
            # Generate GET queries
            if get_endpoints:
                # All GET endpoints
                queries.append("Display all GET endpoints available")
                queries.append("Show me all the GET API endpoints")
                queries.append("What GET requests can I make?")
                
                # Specific GET endpoints
                for endpoint in get_endpoints[:5]:  # Limit to first 5
                    path = endpoint["path"]
                    name = endpoint["name"]
                    
                    if "/posts" in path.lower():
                        queries.append(f"Get all posts using {name}")
                        queries.append(f"Display all posts from {path}")
                        queries.append(f"Show me the posts data")
                    elif "/comments" in path.lower():
                        queries.append(f"Get comments using {name}")
                        queries.append(f"Display comments from {path}")
                    elif "1" in path:
                        queries.append(f"Get single item from {path}")
                        queries.append(f"Show me details for {path}")
                    else:
                        queries.append(f"Call {name} to get data from {path}")
            
            # Generate POST queries
            if post_endpoints:
                queries.append("How do I create a new post?")
                queries.append("Show me how to add new data using POST")
                for endpoint in post_endpoints[:3]:
                    path = endpoint["path"]
                    queries.append(f"Create a new item at {path}")
            
            # Generate PUT/PATCH queries
            if put_endpoints:
                queries.append("How do I update an existing item?")
                queries.append("Show me how to modify data using PUT")
            
            # Generate DELETE queries
            if delete_endpoints:
                queries.append("How do I delete an item?")
                queries.append("Show me how to remove data using DELETE")
            
            # General queries
            queries.append("What APIs are available?")
            queries.append("List all available endpoints")
            queries.append("Show me all the tools I can use")
            queries.append("What can I do with these APIs?")
            
            self.logger.log("QUERY_GENERATOR", f"Generated {len(queries)} queries from {json_file_path}")
            
            return queries
            
        except Exception as e:
            self.logger.log_error("QUERY_GENERATOR", e, {"file": json_file_path})
            return []
    
    def generate_queries_for_tool(self, tool: Dict[str, Any]) -> List[str]:
        """Generate queries for a specific tool"""
        queries = []
        name = tool.get("name", "")
        method = tool.get("method", "").upper()
        path = tool.get("path", "")
        description = tool.get("description", "")
        
        # Method-specific queries
        if method == "GET":
            queries.append(f"Get data from {name}")
            queries.append(f"Display {name} results")
            queries.append(f"Show me {name} data")
            if "all" in name.lower() or "list" in name.lower():
                queries.append(f"Get all items using {name}")
        elif method == "POST":
            queries.append(f"Create new item using {name}")
            queries.append(f"Add data with {name}")
        elif method == "PUT":
            queries.append(f"Update item using {name}")
        elif method == "DELETE":
            queries.append(f"Delete item using {name}")
        
        return queries


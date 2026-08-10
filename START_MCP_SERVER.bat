@echo off
echo ========================================
echo Starting MCP Server
echo ========================================
cd mcp-generator
echo.
echo Starting server on http://127.0.0.1:8504
echo Press CTRL+C to stop the server
echo.
python mcp_server_generated.py
pause


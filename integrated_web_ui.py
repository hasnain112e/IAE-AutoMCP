#!/usr/bin/env python3
"""
Integrated Web UI
Single entry point for all functionality:
- JSON file import
- MCP generation
- Validation
- Chat with APIs
- Query generation
- System logs
"""
import os
import sys
import json
import subprocess
import threading
import time
import asyncio
import socket
from pathlib import Path
from typing import List, Dict, Any, Optional
import streamlit as st
from dotenv import load_dotenv

# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "mcp-generator"))
sys.path.insert(0, str(Path(__file__).parent / "IAE-AutoMCP-Mcp_super_Validator"))

from system_logger import get_logger
from query_generator import QueryGenerator

# Import chat UI functions
from chat_ui import (
    load_tools_from_json_bytes,
    load_tools_from_csv_bytes,
    load_tools_from_uploaded,
    tool_to_openai_schema,
    build_client,
    init_session_state as init_chat_state,
    run_tool_call,
    _http_call
)

try:
    from openai import OpenAI
except ImportError:
    st.error("OpenAI SDK required. Install with: pip install openai")
    st.stop()

load_dotenv()

# Initialize logger
logger = get_logger()
query_gen = QueryGenerator()

# Page config
st.set_page_config(
    page_title="IAE-AutoMCP - Integrated System",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

def init_session_state():
    """Initialize session state"""
    if "tools" not in st.session_state:
        st.session_state.tools: List[Dict[str, Any]] = []
    if "openai_tools" not in st.session_state:
        st.session_state.openai_tools: List[Dict[str, Any]] = []
    if "tools_index" not in st.session_state:
        st.session_state.tools_index: Dict[str, Dict[str, Any]] = {}
    if "global_config" not in st.session_state:
        st.session_state.global_config: Dict[str, Any] = {}
    if "client" not in st.session_state:
        st.session_state.client = None
    if "model_name" not in st.session_state:
        st.session_state.model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if "generated_queries" not in st.session_state:
        st.session_state.generated_queries: List[str] = []
    if "mcp_code" not in st.session_state:
        st.session_state.mcp_code: Optional[str] = None
    if "validation_result" not in st.session_state:
        st.session_state.validation_result: Optional[Dict[str, Any]] = None
    if "system_logs" not in st.session_state:
        st.session_state.system_logs: List[Dict[str, Any]] = []

def check_service_health(service_name: str, port: int) -> bool:
    """Check if a service is running"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', port))
        sock.close()
        return result == 0
    except Exception:
        return False

def start_backend_manually():
    """Start backend server manually"""
    import subprocess
    import os
    from pathlib import Path
    
    project_root = Path(__file__).parent.absolute()
    env = os.environ.copy()
    env['PYTHONPATH'] = str(project_root)
    
    try:
        process = subprocess.Popen(
            ["uvicorn", "api_collector_backend.app:app", "--reload", "--port", "8000", "--host", "0.0.0.0"],
            cwd=str(project_root),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return True, "Backend starting..."
    except Exception as e:
        return False, str(e)

def check_google_adk_installed() -> tuple[bool, str]:
    """Check if Google ADK is installed"""
    try:
        import google.genai
        import google.adk
        return True, "Google ADK is installed"
    except ImportError as e:
        return False, f"Google ADK not installed: {str(e)}. Install with: pip install google-adk"

def generate_mcp_code(api_spec_path: str) -> tuple[bool, str]:
    """Generate MCP code from API spec"""
    try:
        logger.log("UI", f"Generating MCP code from {api_spec_path}")
        
        # Check if Google ADK is installed
        adk_installed, adk_message = check_google_adk_installed()
        if not adk_installed:
            error_msg = f"❌ {adk_message}\n\n" \
                       f"**To fix this:**\n" \
                       f"1. Install Google ADK: `pip install google-adk`\n" \
                       f"2. Or install all dependencies: `pip install -r requirements.txt`\n" \
                       f"3. Make sure you have GOOGLE_API_KEY or GEMINI_API_KEY in your .env file"
            logger.log("UI", "Google ADK not installed; using deterministic generator fallback", {"error": adk_message})

            from shared.mcp_deterministic_generator import generate_mcp_server_code

            with open(api_spec_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            tools = raw.get("tools") if isinstance(raw, dict) else raw
            if not isinstance(tools, list):
                return False, f"Invalid spec format in {api_spec_path}: expected a list or {{\"tools\": [...]}}"

            output_path = "mcp-generator/mcp_server_generated.py"
            code = generate_mcp_server_code(
                tools=tools,
                server_name="Generated MCP Server (Deterministic Fallback)",
                default_spec_filename=os.path.basename(api_spec_path),
            )
            Path(output_path).write_text(code, encoding="utf-8")
            st.session_state.mcp_code = code
            logger.log("UI", "MCP code generated via deterministic fallback", {"output": output_path})
            return True, output_path
        
        # Import generator
        sys.path.insert(0, str(Path(__file__).parent / "mcp-generator"))
        from agent_mcp_generator import generate_mcp_code as gen_code
        
        # Run generation
        output_path = asyncio.run(gen_code(
            api_spec_path=api_spec_path,
            output_path="mcp-generator/mcp_server_generated.py",
            use_super_validator=True,
            validator_url="http://localhost:8002",
            max_validation_iterations=5
        ))
        
        # Read generated code
        with open(output_path, 'r', encoding='utf-8') as f:
            code = f.read()
        
        st.session_state.mcp_code = code
        logger.log("UI", "MCP code generated successfully", {"output": output_path})
        
        return True, output_path
    except ImportError as e:
        if "google.genai" in str(e) or "google.adk" in str(e):
            error_msg = f"❌ Google ADK not installed: {str(e)}\n\n" \
                       f"**Installation:**\n" \
                       f"```bash\npip install google-adk\n```\n\n" \
                       f"Or install all dependencies:\n" \
                       f"```bash\npip install -r requirements.txt\n```"
            logger.log("UI", "Google ADK import failed", {"error": str(e)})
            return False, error_msg
        else:
            logger.log_error("UI", e, {"api_spec": api_spec_path})
            return False, f"Import error: {str(e)}"
    except Exception as e:
        # Last-resort deterministic fallback: keep the UI usable even if the LLM generator fails.
        logger.log_error("UI", e, {"api_spec": api_spec_path, "fallback": "deterministic"})
        try:
            from shared.mcp_deterministic_generator import generate_mcp_server_code

            with open(api_spec_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            tools = raw.get("tools") if isinstance(raw, dict) else raw
            if not isinstance(tools, list):
                return False, f"Invalid spec format in {api_spec_path}: expected a list or {{\"tools\": [...]}}"

            output_path = "mcp-generator/mcp_server_generated.py"
            code = generate_mcp_server_code(
                tools=tools,
                server_name="Generated MCP Server (Deterministic Fallback)",
                default_spec_filename=os.path.basename(api_spec_path),
            )
            Path(output_path).write_text(code, encoding="utf-8")
            st.session_state.mcp_code = code
            return True, output_path
        except Exception as fallback_err:
            logger.log_error("UI", fallback_err, {"api_spec": api_spec_path, "fallback": "failed"})
            return False, str(e)

def validate_code(code: str) -> Dict[str, Any]:
    """Validate MCP code using validator"""
    try:
        import requests
        
        logger.log("UI", "Validating code...", {"code_length": len(code)})
        
        # Check if validator is running first
        if not check_service_health("validator", 8002):
            return {
                "error": "Validator service is not running. Please start it first.",
                "validator_running": False
            }
        
        # Increase timeout for LLM validation
        response = requests.post(
            "http://localhost:8002/validate",
            json={"code": code, "use_llm": True},
            timeout=120  # Increased to 2 minutes for LLM validation
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.log_validation(len(code), result.get("approved", False), result.get("quality_score"))
            return result
        else:
            error_detail = "Unknown error"
            try:
                error_detail = response.json().get("detail", str(response.status_code))
            except:
                error_detail = f"HTTP {response.status_code}"
            return {"error": f"Validation failed: {error_detail}"}
    except requests.exceptions.Timeout:
        return {"error": "Validation timed out. The validator may be processing. Try again in a moment."}
    except requests.exceptions.ConnectionError:
        return {"error": "Cannot connect to validator. Make sure it's running on port 8002."}
    except Exception as e:
        logger.log_error("UI", e)
        return {"error": f"Validation error: {str(e)}"}

def main():
    """Main application"""
    init_session_state()
    
    # Header
    st.title("🚀 IAE-AutoMCP - Integrated System")
    st.markdown("**Single entry point for MCP generation, validation, and API chat**")
    
    # Service status
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        validator_status = "🟢 Running" if check_service_health("validator", 8002) else "🔴 Stopped"
        st.metric("Validator", validator_status)
    with col2:
        backend_running = check_service_health("backend", 8000)
        backend_status = "🟢 Running" if backend_running else "🔴 Stopped"
        st.metric("Backend", backend_status)
        if not backend_running:
            if st.button("▶️ Start Backend", key="start_backend", use_container_width=True):
                with st.spinner("Starting backend..."):
                    success, message = start_backend_manually()
                    if success:
                        st.success(message)
                        time.sleep(2)
                        st.rerun()
                    else:
                        st.error(f"Failed: {message}")
    with col3:
        st.metric("Log File", "📄 " + Path(logger.get_log_file_path()).name)
    with col4:
        if st.button("🔄 Refresh Status", use_container_width=True):
            st.rerun()
    
    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📁 Import & Generate",
        "💬 Chat with APIs",
        "✅ Validate Code",
        "❓ Sample Queries",
        "📊 System Logs"
    ])
    
    # Tab 1: Import & Generate
    with tab1:
        st.header("Import API Spec & Generate MCP Code")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("1. Import JSON File")
            
            # Quick import button for default file
            if st.button("📥 Load Default: jsonplaceholder_typicode_com_api.json", type="primary"):
                default_file = "mcp-generator/jsonplaceholder_typicode_com_api.json"
                if os.path.exists(default_file):
                    with open(default_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    st.session_state.tools = data
                    st.session_state.openai_tools = [tool_to_openai_schema(t) for t in data]
                    st.session_state.tools_index = {t["name"]: t for t in data}
                    st.success(f"✅ Loaded {len(data)} tools from default file!")
                    logger.log("UI", f"Loaded default JSON file", {"tools_count": len(data)})
                else:
                    st.error(f"Default file not found: {default_file}")
            
            st.markdown("---")
            
            # File uploader
            uploaded_file = st.file_uploader(
                "Or upload your own API spec JSON file",
                type=["json"],
                help="Upload API specification in JSON format"
            )
            
            if uploaded_file:
                try:
                    data = load_tools_from_json_bytes(uploaded_file.read())
                    st.session_state.tools = data
                    st.session_state.openai_tools = [tool_to_openai_schema(t) for t in data]
                    st.session_state.tools_index = {t["name"]: t for t in data}
                    st.success(f"✅ Loaded {len(data)} tools!")
                    logger.log("UI", "Loaded uploaded JSON file", {"tools_count": len(data)})
                except Exception as e:
                    st.error(f"Failed to load file: {e}")
                    logger.log_error("UI", e)
        
        with col2:
            st.subheader("2. Generate MCP Code")
            
            # Check Google ADK status
            adk_installed, adk_message = check_google_adk_installed()
            if not adk_installed:
                st.warning(f"⚠️ {adk_message}")
                with st.expander("📦 How to Install Google ADK", expanded=True):
                    st.markdown("""
                    **Install Google ADK:**
                    ```bash
                    pip install google-adk
                    ```
                    
                    **Or install all dependencies:**
                    ```bash
                    pip install -r requirements.txt
                    ```
                    
                    **Also make sure you have:**
                    - `GOOGLE_API_KEY` or `GEMINI_API_KEY` in your `.env` file
                    """)
            
            if st.session_state.tools:
                st.info(f"📊 {len(st.session_state.tools)} tools loaded")
                
                # Save to temp file for generation
                if st.button("🔨 Generate MCP Server Code", type="primary", disabled=not adk_installed):
                    with st.spinner("Generating MCP code... This may take a minute."):
                        # Save tools to temp file
                        temp_file = "temp_api_spec.json"
                        with open(temp_file, 'w', encoding='utf-8') as f:
                            json.dump(st.session_state.tools, f, indent=2)
                        
                        # Generate code
                        success, result = generate_mcp_code(temp_file)
                        
                        if success:
                            st.success("✅ MCP code generated successfully!")
                            st.code(st.session_state.mcp_code[:500] + "..." if len(st.session_state.mcp_code) > 500 else st.session_state.mcp_code, language="python")
                        else:
                            # Show detailed error with markdown
                            st.error("❌ Generation failed")
                            st.markdown(result)  # This will render markdown if it's formatted
            else:
                st.warning("⚠️ Please import an API spec file first")
    
    # Tab 2: Chat with APIs
    with tab2:
        st.header("💬 Chat with Your APIs")
        
        # Initialize chat client
        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            value=os.getenv("OPENAI_API_KEY", ""),
            help="Enter your OpenAI API key"
        )
        
        if api_key:
            st.session_state.client = build_client(api_key)
            if st.session_state.client:
                st.success("✅ OpenAI client ready")
            else:
                st.error("❌ Failed to initialize OpenAI client")
        
        if st.session_state.tools and st.session_state.client:
            st.info(f"🛠️ {len(st.session_state.tools)} tools available")
            
            # Chat interface
            if "messages" not in st.session_state:
                st.session_state.messages = []
            
            # Display chat history
            for msg in st.session_state.messages:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
            
            # Chat input
            if prompt := st.chat_input("Ask something about your APIs..."):
                st.session_state.messages.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)
                
                with st.chat_message("assistant"):
                    with st.spinner("Thinking..."):
                        try:
                            response = st.session_state.client.chat.completions.create(
                                model=st.session_state.model_name,
                                messages=[
                                    {"role": "system", "content": "You are a helpful assistant that can call API tools."},
                                    *[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages],
                                ],
                                tools=st.session_state.openai_tools,
                                tool_choice="auto"
                            )
                            
                            message = response.choices[0].message
                            
                            if message.tool_calls:
                                for tool_call in message.tool_calls:
                                    tool_dict = {
                                        "function": {
                                            "name": tool_call.function.name,
                                            "arguments": json.dumps(json.loads(tool_call.function.arguments))
                                        }
                                    }
                                    result = run_tool_call(
                                        tool_dict,
                                        st.session_state.tools_index,
                                        st.session_state.global_config
                                    )
                                    st.markdown(f"**[Tool {tool_call.function.name} result]** {result[:200]}...")
                            
                            if message.content:
                                st.markdown(message.content)
                                st.session_state.messages.append({"role": "assistant", "content": message.content})
                        except Exception as e:
                            st.error(f"Error: {e}")
                            logger.log_error("UI", e)
        else:
            st.warning("⚠️ Please load tools and configure OpenAI API key")
    
    # Tab 3: Validate Code
    with tab3:
        st.header("✅ Validate MCP Code")
        
        if st.session_state.mcp_code:
            st.subheader("Generated Code")
            st.code(st.session_state.mcp_code, language="python")
            
            # Check validator status
            validator_running = check_service_health("validator", 8002)
            if not validator_running:
                st.warning("⚠️ Validator service is not running. Please start it first.")
                if st.button("▶️ Start Validator", key="start_validator"):
                    with st.spinner("Starting validator..."):
                        # Start validator in background
                        import subprocess
                        project_root = Path(__file__).parent.absolute()
                        env = os.environ.copy()
                        env['PYTHONPATH'] = str(project_root)
                        try:
                            if sys.platform == "win32":
                                subprocess.Popen(
                                    ["python", "IAE-AutoMCP-Mcp_super_Validator/http_server.py", "--port", "8002"],
                                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                                    cwd=str(project_root),
                                    env=env
                                )
                            else:
                                subprocess.Popen(
                                    ["python", "IAE-AutoMCP-Mcp_super_Validator/http_server.py", "--port", "8002"],
                                    cwd=str(project_root),
                                    env=env
                                )
                            st.success("Validator starting... Please wait a few seconds and refresh.")
                            time.sleep(3)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to start validator: {e}")
            
            if st.button("🔍 Validate Code", type="primary", disabled=not validator_running):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                status_text.text("Validating code... This may take 1-2 minutes.")
                progress_bar.progress(10)
                
                result = validate_code(st.session_state.mcp_code)
                progress_bar.progress(100)
                status_text.empty()
                
                st.session_state.validation_result = result
                
                if "error" not in result:
                    st.subheader("Validation Results")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        status = "✅ Approved" if result.get("approved") else "❌ Needs Revision"
                        st.metric("Status", status)
                    with col2:
                        score = result.get("quality_score", "N/A")
                        st.metric("Quality Score", score)
                    with col3:
                        errors_count = len(result.get("errors", []))
                        st.metric("Errors", errors_count)
                    
                    # LLM Validation Details
                    if "llm_validation" in result:
                        llm_val = result["llm_validation"]
                        with st.expander("🧠 LLM Validation Details", expanded=True):
                            if "reasoning" in llm_val:
                                st.markdown("**Reasoning:**")
                                st.text(llm_val["reasoning"])
                            if "risk_assessment" in llm_val:
                                st.markdown("**Risk Assessment:**")
                                st.text(llm_val["risk_assessment"])
                            if "improvements" in llm_val:
                                st.markdown("**Improvements:**")
                                for imp in llm_val["improvements"]:
                                    st.markdown(f"- {imp}")
                else:
                    st.error(f"Validation error: {result['error']}")
        else:
            st.info("ℹ️ Generate MCP code first in the 'Import & Generate' tab")
    
    # Tab 4: Sample Queries
    with tab4:
        st.header("❓ Generate Sample Queries")
        
        if st.session_state.tools:
            if st.button("🎲 Generate Sample Queries", type="primary"):
                # Save to temp file
                temp_file = "temp_api_spec.json"
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(st.session_state.tools, f, indent=2)
                
                queries = query_gen.generate_queries_from_json(temp_file)
                st.session_state.generated_queries = queries
                logger.log("UI", f"Generated {len(queries)} sample queries")
            
            if st.session_state.generated_queries:
                st.success(f"✅ Generated {len(st.session_state.generated_queries)} sample queries")
                st.markdown("**Click any query to use it in chat:**")
                
                for i, query in enumerate(st.session_state.generated_queries[:20]):  # Show first 20
                    if st.button(query, key=f"query_{i}", use_container_width=True):
                        # Add to chat
                        if "messages" not in st.session_state:
                            st.session_state.messages = []
                        st.session_state.messages.append({"role": "user", "content": query})
                        st.rerun()
        else:
            st.warning("⚠️ Please import an API spec file first")
    
    # Tab 5: System Logs
    with tab5:
        st.header("📊 System Logs")
        
        if st.button("🔄 Refresh Logs"):
            st.session_state.system_logs = logger.get_recent_logs(limit=100)
        
        if st.session_state.system_logs:
            st.info(f"Showing {len(st.session_state.system_logs)} recent log entries")
            
            # Filter by component
            components = list(set(log.get("component", "UNKNOWN") for log in st.session_state.system_logs))
            selected_component = st.selectbox("Filter by component", ["ALL"] + sorted(components))
            
            # Display logs
            filtered_logs = st.session_state.system_logs
            if selected_component != "ALL":
                filtered_logs = [log for log in filtered_logs if log.get("component") == selected_component]
            
            for log in filtered_logs[-50:]:  # Show last 50
                with st.expander(f"[{log.get('component', 'UNKNOWN')}] {log.get('message', '')}", expanded=False):
                    st.json(log)
        else:
            st.info("No logs yet. System activity will appear here.")

if __name__ == "__main__":
    main()


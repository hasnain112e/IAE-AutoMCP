# 🚀 IAE-AutoMCP (MCPValidator3)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg" alt="Python Version" />
  <img src="https://img.shields.io/badge/FastAPI-0.100%2B-green.svg" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-18%2B-61dafb.svg" alt="React" />
  <img src="https://img.shields.io/badge/MCP-FastMCP-orange.svg" alt="FastMCP" />
  <img src="https://img.shields.io/badge/License-MIT-purple.svg" alt="License" />
</p>

> **Autonomous Multi-Agent MCP Server Generator & Intelligent Quality Validator**

**IAE-AutoMCP** (MCPValidator3) is an advanced, production-grade multi-agent platform designed to automatically generate, validate, score, and iteratively improve Model Context Protocol (MCP) server code from API specifications, OpenAPI/Swagger specs, Postman collections, or standard tool schemas.

---

## ✨ Key Features

- 🤖 **Automated MCP Code Generation**: Transforms OpenAPI specs, Postman collections, and API endpoints into fully compliant FastMCP python servers.
- 🔬 **4-Layer Compliance Inspector**: Validates Python syntax, static analysis (Ruff), MCP protocol structure, runtime safety, and performance metrics.
- 🔄 **Intelligent Feedback-Loop Regeneration**: Iteratively fixes code errors with actionable instructions until quality score threshold ($\ge 80$) is achieved.
- 📡 **Real-Time Telemetry & WebSocket Agent Monitor**: Live monitoring of Agent-to-Agent (A2A) inter-process communications and status updates.
- 🎯 **No Score-0 Fallback (MIN_SCORE Gradient)**: Uses dynamic minimum scoring ($\ge 10$) and improvement tracking to guarantee learning curves between iterations.
- 🖥️ **Integrated Web GUI & Agent Management**: Built-in batch launcher scripts and rich Web UI to control the multi-agent ecosystem with a single click.

---

## 🏗️ Multi-Agent Architecture

The system operates via five coordinated specialized agents communicating over the **A2A (Agent-to-Agent)** HTTP/WebSocket Protocol:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      IAE-AutoMCP System Architecture                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌────────────────┐      ┌────────────────┐      ┌──────────────────┐  │
│  │    Frontend    │◄────►│ Background API │◄────►│ Validator Agent  │  │
│  │ (React / Vite) │      │ (FastAPI:8000) │      │   (Port 8002)    │  │
│  └────────────────┘      └────────────────┘      └──────────────────┘  │
│          ▲                        ▲                       ▲             │
│          │                        │                       │             │
│          ▼                        ▼                       ▼             │
│  ┌────────────────┐      ┌────────────────┐      ┌──────────────────┐  │
│  │ UI Controller  │◄────►│ Orchestrator   │◄────►│ Generator Agent  │  │
│  │  (Port 8102)   │      │  (Port 8100)   │      │   (Port 8101)    │  │
│  └────────────────┘      └────────────────┘      └──────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Agent Roles & Service Ports

| Service / Agent | Default Port | Role & Responsibility |
| :--- | :---: | :--- |
| **Backend Service** | `8000` | API Collection, OpenAPI parsing, JSON tool schema extraction |
| **Validator Agent** | `8002` | Code inspection, static analysis, Ruff linting, scoring engine |
| **Orchestrator Agent** | `8100` | Process pipeline coordination, state persistence, iteration loops |
| **Generator Agent** | `8101` | LLM code generation, patch application & prompt engineering |
| **UI Controller Agent** | `8102` | Telemetry logging, WebSocket broadcasting, live agent status |
| **Frontend Web App** | `3000` | Modern React UI dashboard |

---

## ⚡ Quick Start

### 1. Prerequisites
- **Python**: `3.10+` (3.11 recommended)
- **Node.js**: `18+` & `npm`
- **OpenAI API Key**: Required for generation capabilities

### 2. Installation

```bash
# Clone repository
git clone https://github.com/hasnain112e/IAE-AutoMCP.git
cd IAE-AutoMCP

# Set up Python Virtual Environment
python -m venv .venv
# On Windows PowerShell:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install Frontend dependencies
cd api_collector_frontend
npm install
cd ..
```

### 3. Environment Configuration

Copy `.env.example` to `.env` and insert your API key:

```env
OPENAI_API_KEY=sk-your-openai-api-key-here
OPENAI_MODEL=gpt-4o
```

### 4. Running the Application

#### Windows (One-Click Batch Script):
Simply double-click or run:
```cmd
START_EVERYTHING.bat
```
*(Or use `START_ALL.bat` / `run.bat`)*

#### Manual / Cross-Platform Command:
```bash
# Launch background agents
python launch_agents.py

# In a separate terminal, launch Web UI
cd api_collector_frontend
npm run dev
```

Open your browser at: **`http://localhost:3000`**

---

## 📖 Usage Guide

1. **Provide Input**: Upload OpenAPI JSON/YAML, Postman Collection, raw tool JSON, or paste endpoint URLs.
2. **Generate**: Click **Generate MCP Server**. The Backend extracts tools and sends them to the Generator Agent.
3. **Inspect & Score**: The Validator Agent runs a 4-layer inspection, issuing quality scores (0-100) and actionable fix suggestions.
4. **Auto-Improve**: If score $< 80$, click **Auto Run** to automatically iterate code generation until quality requirements are satisfied.
5. **Export**: Export validated production-ready FastMCP Python code.

---

## 📁 Repository Structure

```
IAE-AutoMCP/
├── agents/                       # Agent implementations
│   ├── validator/                # Validator agent & scoring engine
│   ├── orchestrator/             # Pipeline controller agent
│   ├── generator/                # Code generation agent
│   └── ui_controller/            # Real-time WebSocket telemetry agent
├── api_collector_backend/        # FastAPI spec parser & collector
├── api_collector_frontend/       # React + Vite frontend UI
├── shared/                       # Agent-to-Agent (A2A) protocol & data models
├── mcp-generator/                # MCP generation tools
├── md/                           # Documentation & architecture specs
├── START_EVERYTHING.bat          # 1-click startup script for Windows
├── launch_agents.py              # Cross-platform python agent launcher
├── requirements.txt              # Python requirements
└── README.md                     # Main GitHub documentation
```

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [Issues Page](https://github.com/hasnain112e/IAE-AutoMCP/issues).

---

## 📜 License

This project is licensed under the [MIT License](LICENSE).

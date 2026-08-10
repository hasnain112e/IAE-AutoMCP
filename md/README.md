# MCPValidator3

**AI-Powered MCP Server Generator with Intelligent Validation**

An advanced multi-agent system that automatically generates, validates, and iteratively improves Model Context Protocol (MCP) server code from API specifications.

---

## 🌟 Features

### Core Capabilities
- **🤖 Automatic MCP Server Generation** - Generate complete MCP servers from API specs, OpenAPI, Postman collections, or tool definitions
- **✅ Multi-Layer Validation** - Comprehensive validation including syntax, static analysis, MCP compliance, and regression checking
- **🔄 Intelligent Iterative Improvement** - Automatic code regeneration with actionable fix instructions (never score=0)
- **📊 Real-Time Telemetry** - Live progress tracking and agent communication monitoring via WebSocket
- **🎯 Smart Error Recovery** - Provides fix instructions and regeneration hints instead of rejection
- **🔍 MCP Compliance Inspector** - 4-layer validation ensuring FastMCP protocol standards

### Key Innovations
- **MIN_SCORE Philosophy** - Even worst code gets score=10 to enable learning gradient
- **Fix Instructions Generation** - Actionable guidance for code improvement
- **Improvement Signals Tracking** - Monitors progress across iterations
- **Regression Detection** - Prevents quality degradation between iterations

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MCPValidator3 System                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐  │
│  │   Frontend   │◄────►│   Backend    │◄────►│  Validator   │  │
│  │  (React/TS)  │      │  (FastAPI)   │      │    Agent     │  │
│  └──────────────┘      └──────────────┘      └──────────────┘  │
│         │                      │                      │         │
│         │                      │                      │         │
│         ▼                      ▼                      ▼         │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐  │
│  │UI Controller │◄────►│ Orchestrator │◄────►│  Generator   │  │
│  │    Agent     │      │    Agent     │      │    Agent     │  │
│  └──────────────┘      └──────────────┘      └──────────────┘  │
│                                                                 │
│  Communication: A2A Protocol (Agent-to-Agent) over HTTP/WS     │
└─────────────────────────────────────────────────────────────────┘
```

### Agent Responsibilities

| Agent | Port | Role |
|-------|------|------|
| **Backend** | 8000 | API collection, file parsing, tool extraction |
| **Validator** | 8002 | Code validation, quality scoring, MCP compliance |
| **Orchestrator** | 8100 | Pipeline coordination, state management, iteration control |
| **Generator** | 8101 | LLM-based code generation, fix application |
| **UI Controller** | 8102 | Real-time telemetry, WebSocket communication |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+** (3.11 recommended)
- **Node.js 18+** (for frontend)
- **OpenAI API Key** (required for LLM features)
- **Git** (for cloning)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/MCPValidator3.git
cd MCPValidator3
```

2. **Set up Python environment**
```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

3. **Configure environment**
```bash
# Copy environment template
copy .env.example .env  # Windows
# or
cp .env.example .env    # Linux/Mac

# Edit .env and add your OpenAI API key
# OPENAI_API_KEY=sk-your-key-here
```

4. **Install frontend dependencies**
```bash
cd api_collector_frontend
npm install
cd ..
```

### Running the System

#### Option 1: Windows Batch File (Recommended for Windows)
```bash
START_EVERYTHING.bat
```

This will:
- Start all 5 agent services
- Launch the frontend development server
- Open your browser to http://localhost:3000

#### Option 2: Python Launcher (Cross-platform)
```bash
python launch_agents.py
```

Then in a separate terminal:
```bash
cd api_collector_frontend
npm run dev
```

#### Option 3: Manual Start (For debugging)
```bash
# Terminal 1 - Backend
cd api_collector_backend
python -m uvicorn app:app --host 0.0.0.0 --port 8000

# Terminal 2 - Validator
python -m agents.validator.validator_agent

# Terminal 3 - Orchestrator
python -m agents.orchestrator.orchestrator_agent

# Terminal 4 - Generator
python -m agents.generator.generator_agent

# Terminal 5 - UI Controller
python -m agents.ui_controller.ui_controller_agent

# Terminal 6 - Frontend
cd api_collector_frontend
npm run dev
```

### Stopping the System

#### Windows:
```bash
STOP_EVERYTHING.bat
```

#### Linux/Mac:
```bash
# Press Ctrl+C in each terminal
# Or use:
pkill -f "python.*agent"
pkill -f "npm run dev"
```

---

## 📖 Usage

### Basic Workflow

1. **Open the UI** at http://localhost:3000

2. **Provide API Input** (choose one):
   - Upload OpenAPI/Swagger JSON
   - Upload Postman collection
   - Paste API documentation URL
   - Upload tools.json file
   - Manually define tools

3. **Click "Generate MCP Server"**
   - System extracts tools from input
   - Generator creates initial MCP server code
   - Validator checks code quality

4. **Review Validation Results**
   - View quality score (0-100)
   - See errors, warnings, and suggestions
   - Check MCP compliance issues

5. **Automatic Improvement** (if score < 80)
   - System provides fix instructions
   - Generator creates improved version
   - Process repeats (max 5 iterations)

6. **Download Result** (when score ≥ 80)
   - Download validated MCP server code
   - View iteration history
   - Check telemetry logs

### Auto Run Feature

Click the **"Auto Run"** button to:
- Automatically iterate until score ≥ 80
- Stop at max 5 iterations
- No manual intervention required
- View real-time progress

---

## 🔧 Configuration

### Environment Variables

See `.env.example` for all available options. Key variables:

```bash
# Required
OPENAI_API_KEY=sk-your-key-here

# Optional (with defaults)
OPENAI_MODEL=gpt-4o                # LLM model to use
BACKEND_PORT=8000                  # Backend service port
VALIDATOR_PORT=8002                # Validator service port
ORCHESTRATOR_PORT=8100             # Orchestrator service port
GENERATOR_PORT=8101                # Generator service port
UI_CONTROLLER_PORT=8102            # UI Controller service port

# Limits
MAX_CODE_SIZE=1000000              # 1MB max code size
MAX_LINES=10000                    # Max lines per file
MAX_ITERATIONS=5                   # Max regeneration attempts

# Scoring
MIN_SCORE=10                       # Minimum score (never 0)
APPROVAL_THRESHOLD=80              # Score needed for approval
```

### Service Ports

All services run on localhost. Default ports:

| Service | Port | URL |
|---------|------|-----|
| Frontend | 3000 | http://localhost:3000 |
| Backend | 8000 | http://localhost:8000 |
| Validator | 8002 | http://localhost:8002 |
| Orchestrator | 8100 | http://localhost:8100 |
| Generator | 8101 | http://localhost:8101 |
| UI Controller | 8102 | http://localhost:8102 |

---

## 📚 Documentation

- **[Architecture Overview](md/ARCHITECTURE.md)** - System design and agent interactions
- **[API Reference](md/API.md)** - Endpoint documentation
- **[Configuration Guide](md/CONFIGURATION.md)** - Environment setup details
- **[Troubleshooting](md/TROUBLESHOOTING.md)** - Common issues and solutions
- **[Development Guide](md/DEVELOPMENT.md)** - Contributing and development setup
- **[Improvement Plan](md/IMPROVEMENT_PLAN.md)** - Planned enhancements

---

## 🧪 Testing

### Run Unit Tests
```bash
pytest agents/validator/tests/ -v
```

### Run Integration Tests
```bash
pytest tests/integration/ -v
```

### Run All Tests with Coverage
```bash
pytest --cov=agents --cov=shared --cov-report=html
```

### View Coverage Report
```bash
# Open htmlcov/index.html in browser
```

---

## 🛠️ Development

### Project Structure

```
MCPValidator3/
├── agents/                      # Agent implementations
│   ├── base_agent.py           # Base agent class
│   ├── validator/              # Validator agent
│   │   ├── validator_agent.py
│   │   ├── mcp_compliance.py   # MCP inspector
│   │   ├── scoring_engine.py   # Quality scoring
│   │   ├── ruff_integration.py # Auto-fix integration
│   │   └── tests/              # Unit tests
│   ├── orchestrator/           # Orchestrator agent
│   ├── generator/              # Generator agent
│   └── ui_controller/          # UI Controller agent
├── api_collector_backend/      # Backend service
├── api_collector_frontend/     # React frontend
├── shared/                     # Shared utilities
│   ├── a2a_protocol.py        # Agent communication
│   ├── message_types.py       # Data models
│   ├── config.py              # Configuration
│   └── constants.py           # Constants
├── mcp-generator/             # MCP generation tools
├── md/                        # Documentation
├── requirements.txt           # Python dependencies
├── .env.example              # Environment template
└── launch_agents.py          # Agent launcher
```

### Adding a New Agent

1. Create agent file in `agents/your_agent/`
2. Inherit from `BaseAgent`
3. Implement `handle_message()` method
4. Register in `launch_agents.py`
5. Add tests in `agents/your_agent/tests/`

### Code Quality Tools

```bash
# Format code
black agents/ shared/

# Sort imports
isort agents/ shared/

# Lint code
ruff check agents/ shared/

# Type check
mypy agents/ shared/
```

---

## 🐛 Troubleshooting

### Common Issues

**1. "OpenAI API key not found"**
```bash
# Solution: Set OPENAI_API_KEY in .env file
echo "OPENAI_API_KEY=sk-your-key-here" >> .env
```

**2. "Port already in use"**
```bash
# Solution: Change port in .env or kill existing process
# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/Mac:
lsof -ti:8000 | xargs kill -9
```

**3. "Ruff not found"**
```bash
# Solution: Install Ruff
pip install ruff
```

**4. "Frontend won't start"**
```bash
# Solution: Reinstall dependencies
cd api_collector_frontend
rm -rf node_modules package-lock.json
npm install
```

**5. "Agents not communicating"**
```bash
# Solution: Check all agents are running
# Visit health endpoints:
curl http://localhost:8000/health
curl http://localhost:8002/health
curl http://localhost:8100/health
curl http://localhost:8101/health
curl http://localhost:8102/health
```

For more issues, see [Troubleshooting Guide](md/TROUBLESHOOTING.md)

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](md/CONTRIBUTING.md) for guidelines.

### Development Setup

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run quality checks
6. Submit a pull request

### Code Standards

- Follow PEP 8 style guide
- Add type hints to all functions
- Write docstrings for public APIs
- Maintain test coverage >80%
- Update documentation

---

## 📄 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **FastMCP** - MCP protocol implementation
- **OpenAI** - GPT models for code generation
- **Ruff** - Fast Python linter and formatter
- **FastAPI** - Modern web framework
- **React** - Frontend framework

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/MCPValidator3/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/MCPValidator3/discussions)
- **Email**: support@mcpvalidator3.com

---

## 🗺️ Roadmap

### Current Version: 1.0.0

### Planned Features:
- [ ] Support for more LLM providers (Anthropic, Google)
- [ ] Template-based generation (no LLM required)
- [ ] Custom validation rules
- [ ] Plugin system for validators
- [ ] Docker containerization
- [ ] Cloud deployment support
- [ ] Multi-language support (TypeScript, Go)
- [ ] Visual code editor integration
- [ ] Batch processing mode
- [ ] API rate limiting and caching

See [IMPROVEMENT_PLAN.md](md/IMPROVEMENT_PLAN.md) for detailed roadmap.

---

## 📊 Statistics

- **Lines of Code**: ~15,000
- **Test Coverage**: 80%+
- **Agents**: 5
- **Validation Layers**: 4
- **Supported Input Formats**: 5+
- **Average Generation Time**: 30-60 seconds
- **Success Rate**: 95%+ (score ≥ 80)

---

**Built with ❤️ by the MCPValidator3 Team**

*Making MCP server development intelligent, automated, and reliable.*

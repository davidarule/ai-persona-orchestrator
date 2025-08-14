# AI Persona Orchestrator

A comprehensive visual workflow orchestration system for managing AI personas in DevOps environments. This system enables multiple AI agents to collaborate on software development tasks through Azure DevOps integration, with real-time monitoring and visual workflow management.

## 🎯 Overview

The AI Persona Orchestrator provides:
- **Visual workflow management** for 25+ AI personas
- **Real-time monitoring** of AI agent activities
- **Azure DevOps integration** for work item management
- **Hierarchical workflow orchestration** with 18 system workflows
- **BPMN-based process automation** using Camunda
- **Distributed execution** with fault tolerance
- **Comprehensive monitoring** with Grafana and Prometheus

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React)                        │
│                   Port 3020 - Visual UI                     │
└─────────────────-───┬───────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│                   Backend API (FastAPI)                     │
│                    Port 8000 - REST API                     │
└────────┬─────────────────────┬───────────────-───┬──────-───┘
         │                     │                   │
┌────────┴────────┐   ┌────────┴────────┐  ┌───────┴────────┐
│   PostgreSQL    │   │     Redis       │  │     Neo4j      │
│   Port 5434     │   │   Port 6379     │  │  Port 7474     │
│   Workflows     │   │   Pub/Sub       │  │  Graph Data    │
└─────────────────┘   └─────────────────┘  └────────────────┘
         │
┌────────┴────────────────────────────────────────────────────┐
│                    Camunda Platform                         │
│         Zeebe (26500) | Operate (8081) | Tasklist (8082)    │
└─────────────────────────────────────────────────────────────┘
         │
┌────────┴────────────────────────────────────────────────────┐
│                     Monitoring Stack                        │
│         Grafana (3021) | Prometheus (9091)                  │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Technology Stack

### Core Technologies
- **Frontend**: React 18 with ReactFlow for workflow visualization
- **Backend**: FastAPI (Python 3.12) with async support
- **Databases**: 
  - PostgreSQL 16 (workflow definitions and state)
  - Neo4j 5.19 (graph-based workflow relationships)
  - Redis 7 (pub/sub and caching)
  - Elasticsearch 8.13 (Camunda event storage)

### Orchestration
- **Camunda Platform 8.5**: BPMN workflow engine
- **LangGraph**: AI agent coordination
- **LangChain**: LLM integration framework

### AI Integration
- **Multi-Model Support**: OpenAI GPT, Anthropic Claude, Google Gemini, Grok
- **25 Specialized AI Personas**: From developers to architects
- **18 System Workflows**: Complete DevOps lifecycle automation

### Monitoring
- **Grafana**: Visual dashboards
- **Prometheus**: Metrics collection
- **Custom dashboards**: Real-time agent status

## 📋 Prerequisites

- Ubuntu Server 22.04+ or compatible Linux
- Docker and Docker Compose v2
- Python 3.12+
- Node.js 20+
- 8GB RAM minimum (16GB recommended)
- 20GB free disk space

## 🔧 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/davidarule/ai-persona-orchestrator.git
cd ai-persona-orchestrator
```

### 2. Configure Environment

Copy and edit the environment file:

```bash
cp .env.example .env
nano .env
```

Required environment variables:

```env
# Azure DevOps
AZURE_DEVOPS_ORG_URL=https://dev.azure.com/YOUR_ORG
AZURE_DEVOPS_PAT=your_pat_token

# AI Model APIs (at least one required)
OPENAI_API_KEY=sk-your_key
ANTHROPIC_API_KEY=sk-ant-your_key
GEMINI_API_KEY=your_key
GROK_API_KEY=your_key

# Database Passwords (change these!)
POSTGRES_PASSWORD=secure_password
NEO4J_AUTH=neo4j/secure_password
REDIS_PASSWORD=secure_password

# Security
JWT_SECRET=generate_secure_secret
GRAFANA_PASSWORD=admin_password
```

### 3. Start Services

```bash
# Start core databases
docker compose up -d postgres redis neo4j elasticsearch

# Wait for initialization (30 seconds)
sleep 30

# Start application services
docker compose up -d backend frontend

# Start monitoring
docker compose up -d grafana prometheus

# Start Camunda workflow engine
docker compose -f docker-compose.yml -f docker/docker-compose.camunda.yml up -d
```

### 4. Load Workflows

```bash
# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install asyncpg pyyaml requests python-dotenv

# Load all workflows
python3 scripts/load_workflows.py
```

### 5. Verify Installation

Check all services are running:

```bash
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
```

## 🌐 Access Points

| Service | URL | Description |
|---------|-----|-------------|
| **Frontend Dashboard** | http://localhost:3020 | Main visual interface |
| **Backend API** | http://localhost:8000 | REST API |
| **API Documentation** | http://localhost:8000/docs | Swagger UI |
| **Camunda Operate** | http://localhost:8081 | Workflow monitoring |
| **Camunda Tasklist** | http://localhost:8082 | Task management |
| **Grafana** | http://localhost:3021 | Metrics dashboards |
| **Prometheus** | http://localhost:9091 | Metrics explorer |
| **Neo4j Browser** | http://localhost:7474 | Graph database UI |

## 📚 Workflows

### System Workflows (18)

The system includes 18 core workflows for DevOps operations:

| ID | Workflow | Description |
|----|----------|-------------|
| wf0 | Feature Development | End-to-end feature development process |
| wf1 | Bug Fix | Bug fixing with verification |
| wf2 | Hotfix | Emergency production fixes (4-hour SLA) |
| wf3 | Branch Creation | Standardized branch naming |
| wf4 | Code Commit | Conventional commit standards |
| wf5 | Pull Request Creation | Automated PR with reviewers |
| wf6 | Pull Request Review | Code review process |
| wf7 | Pull Request Response | Feedback handling |
| wf8 | Merge | Smart merge strategies |
| wf9 | Post-Merge Monitoring | Production monitoring |
| wf10 | Conflict Resolution | Automated conflict handling |
| wf11 | Rollback | Emergency rollback procedures |
| wf12 | Work Item Update | Azure DevOps synchronization |
| wf13 | PR Readiness Check | Pre-PR validation |
| wf14 | Build Failure Recovery | Automated build fixes |
| wf15 | Factory Settings Lookup | Configuration management |
| wf16 | Reviewer Selection | Smart reviewer assignment |
| wf17 | Merge Strategy Selection | Context-aware merging |

### AI Personas (25)

Specialized AI agents for different roles:

**Development Team**
- Senior Developer
- Backend Developer
- Frontend Developer
- Mobile Developer
- AI Engineer

**Quality & Testing**
- QA Test Engineer
- Software QA
- Test Engineer
- Integration Engineer

**Architecture & Design**
- Software Architect
- Systems Architect
- Security Architect
- UI/UX Designer

**Operations & Infrastructure**
- DevSecOps Engineer
- Site Reliability Engineer
- Cloud Engineer
- Configuration Release Engineer

**Management & Analysis**
- Engineering Manager
- Product Owner
- Scrum Master
- Business Analyst
- Requirements Analyst

**Specialized Roles**
- Security Engineer
- Data Engineer/DBA
- Technical Writer

## 🔄 Workflow Execution

### Starting a Feature Development Workflow

```python
import requests

# Start a new feature development workflow
response = requests.post("http://localhost:8000/api/workflow/execute", json={
    "work_item_id": "FEAT-123",
    "workflow_type": "feature_development",
    "assigned_agents": {
        "developer": "senior_developer",
        "reviewer": "code_reviewer",
        "tester": "qa_engineer"
    }
})

workflow_id = response.json()["workflow_id"]
print(f"Started workflow: {workflow_id}")
```

### Monitoring Workflow Status

```python
# Check workflow status
status = requests.get(f"http://localhost:8000/api/workflow/status/FEAT-123")
print(status.json())
```

## 📊 Monitoring

### Grafana Dashboards

Access Grafana at http://localhost:3021 (default: admin/admin)

Available dashboards:
- **AI Orchestrator Overview**: System health and metrics
- **Agent Performance**: Individual agent metrics
- **Workflow Analytics**: Execution times and success rates
- **Resource Utilization**: System resource usage

### Prometheus Metrics

Query metrics at http://localhost:9091

Key metrics:
- `workflow_execution_duration`: Workflow completion times
- `agent_task_count`: Tasks per agent
- `api_request_rate`: API request rates
- `database_connections`: Database pool status

## 🧪 Testing Infrastructure

The AI Persona Orchestrator includes a comprehensive testing framework with both static and dynamic test dashboards for real-time monitoring and control.

### Test Dashboard System

#### Starting the Test Services

```bash
# Start both test dashboard services
make dashboard

# Or manually:
bash scripts/start_test_services.sh
```

#### Accessing the Dashboards

| Dashboard | URL | Description |
|-----------|-----|-------------|
| **Landing Page** | http://localhost:8090/ | Choose between static and dynamic dashboards |
| **Static Dashboard** | http://localhost:8090/test_dashboard/ | View latest test results, auto-refreshes every 30 seconds |
| **Dynamic Dashboard** | http://localhost:8090/dynamic | Real-time test execution with live logs |

#### Dynamic Dashboard Features

The dynamic dashboard provides:
- **Real-time test execution** - Start/stop tests with a single click
- **Test type selection** - Choose All, Unit, Integration, or E2E tests
- **Live log streaming** - Watch test output as it happens
- **Progress tracking** - Visual progress bar and statistics
- **Auto-scroll control** - Toggle to follow log output
- **WebSocket updates** - Real-time connection status
- **Color-coded output** - Easy identification of passes, failures, and errors

#### Running Tests

```bash
# Run all tests with HTML report
make test-report

# Run specific test suites
make test-unit          # Unit tests only
make test-integration   # Integration tests only
make test-e2e          # End-to-end tests only

# Run with coverage
make test-coverage

# Stop dashboard services
make dashboard-stop
```

#### Test Organization

The test suite includes:
- **Unit Tests** (27 tests) - Test individual components
- **Integration Tests** (13 tests) - Test database connections and services
- **E2E Tests** (6 tests) - Test complete API endpoints

#### Test Reports

After running tests, access detailed reports:
- **Test Report**: `test_reports/latest/pytest_report.html`
- **Coverage Report**: `test_reports/latest/coverage/index.html`
- **JUnit XML**: `test_reports/latest/junit.xml`

#### Architecture

The test infrastructure consists of:

1. **Test Runner Service** (`scripts/test_runner_service.py`)
   - WebSocket server on port 8765
   - Manages test execution
   - Streams output in real-time
   - Parses test results

2. **Dashboard HTTP Server** (`scripts/test_dashboard_server.py`)
   - HTTP server on port 8090
   - Serves both dashboards
   - Provides test statistics API

3. **Test Dashboards**
   - Static: `test_dashboard/index.html`
   - Dynamic: `test_dashboard/dashboard.html`

### Test Requirements

- Python 3.11+ with pytest
- WebSocket support (websockets package)
- Environment variables from `.env`
- Running database services

### Continuous Integration

The project includes GitHub Actions workflow for automated testing:

```yaml
# .github/workflows/tests.yml
- Runs on push to main/develop
- Sets up test databases
- Executes full test suite
- Generates coverage reports
- Posts results to PRs
```

## 🛠️ Development

### Project Structure

```
ai-persona-orchestrator/
├── backend/                 # FastAPI backend
│   ├── api/                # API endpoints
│   ├── agents/             # AI agent implementations
│   └── orchestration/      # LangGraph orchestration
├── frontend/               # React frontend
│   ├── src/               # React components
│   └── public/            # Static assets
├── workflows/              # Workflow definitions
│   ├── system/            # System workflows (wf0-wf17)
│   └── personas/          # AI persona workflows
├── docker/                 # Docker configurations
├── monitoring/             # Monitoring configs
│   ├── grafana/          # Grafana dashboards
│   └── prometheus/       # Prometheus configs
├── scripts/               # Utility scripts
└── nginx/                # Nginx configuration
```

### Adding a New AI Persona

1. Create workflow YAML in `workflows/personas/`
2. Load into database: `python3 scripts/load_workflows.py`
3. Update agent factory in `backend/agents/agent_factory.py`

### Creating Custom Workflows

Workflows use YAML with this structure:

```yaml
metadata:
  id: unique-id
  name: Workflow Name
  version: 1.0.0
  type: master|core
  description: Description

inputs:
  - name: INPUT_NAME
    type: string|enum|boolean
    required: true

steps:
  - id: step-1
    name: Step Name
    action: execute-workflow|shell-command|git-operation
    inputs:
      key: value

outputs:
  - name: OUTPUT_NAME
    value: ${steps.step-1.output}
```

## 🔒 Security

- All services run in Docker with network isolation
- PostgreSQL uses strong passwords
- API authentication via JWT tokens
- Azure DevOps PAT tokens stored securely
- SSL/TLS support for production deployment

## 🐛 Troubleshooting

### Common Issues

**Port Conflicts**
```bash
# Check what's using a port
sudo lsof -i :PORT_NUMBER

# Change port in docker-compose.yml
sed -i 's/"OLD_PORT:/"NEW_PORT:/g' docker-compose.yml
```

**Database Connection Issues**
```bash
# Test PostgreSQL connection
docker compose exec postgres psql -U orchestrator_user -d ai_orchestrator

# Check logs
docker compose logs postgres
```

**Service Not Starting**
```bash
# Check service logs
docker compose logs SERVICE_NAME

# Restart service
docker compose restart SERVICE_NAME
```

### Reset Everything

```bash
# Stop all services
docker compose down

# Remove all data (WARNING: Deletes everything!)
sudo rm -rf data/

# Recreate data directories
mkdir -p data/{postgres,neo4j,redis,elasticsearch,grafana,prometheus}

# Start fresh
docker compose up -d
```

## 📝 API Documentation

Full API documentation available at http://localhost:8000/docs

Key endpoints:

- `GET /` - Health check
- `POST /api/workflow/execute` - Start workflow
- `GET /api/workflow/status/{work_item_id}` - Check status
- `GET /api/workflow/structure` - Get workflow structure
- `WebSocket /ws/workflow-updates` - Real-time updates

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built with Camunda Platform for workflow orchestration
- LangChain and LangGraph for AI coordination
- ReactFlow for workflow visualization
- FastAPI for high-performance API
- Docker for containerization

## 📧 Support

For issues, questions, or suggestions:
- Create an issue on GitHub
- Check existing documentation
- Review workflow examples in `/workflows`

---

**Project Status**: ✅ Production Ready

**Version**: 1.0.0

**Last Updated**: August 2025
EOF

echo "✅ Created comprehensive README.md"
```

Now let's commit this important documentation:

```bash
git add README.md
git commit -m "Add comprehensive README documentation"
git push
```

This README provides complete documentation for your AI Persona Orchestrator system!

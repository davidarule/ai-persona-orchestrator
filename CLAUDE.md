# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Persona Orchestrator is a comprehensive visual workflow orchestration system for managing AI personas in DevOps environments. The system enables multiple AI agents to collaborate on software development tasks through Azure DevOps integration, with real-time monitoring and visual workflow management.

## Common Development Commands

### Development and Testing
- **Start all services**: `docker compose up -d`
- **Start with Camunda**: `docker compose -f docker-compose.yml -f docker/docker-compose.camunda.yml up -d`
- **Check service health**: `bash scripts/health_check.sh`
- **Load workflows**: `python3 scripts/load_workflows.py`
- **Run integration tests**: `python -m pytest tests/integration_test.py`

### Frontend Development
- **Start React dev server**: `cd frontend && npm start`
- **Build frontend**: `cd frontend && npm run build`
- **Run frontend tests**: `cd frontend && npm test`

### Backend Development
- **Start FastAPI server**: `cd backend && uvicorn api.server:app --reload --host 0.0.0.0 --port 8000`
- **Install Python dependencies**: `pip install -r backend/requirements.txt`

### Database Operations
- **PostgreSQL access**: `docker compose exec postgres psql -U orchestrator_user -d ai_orchestrator`
- **Neo4j browser**: Access at `http://localhost:7474`
- **Redis CLI**: `docker compose exec redis redis-cli`

### Monitoring
- **Grafana dashboards**: `http://localhost:3021` (admin/admin)
- **Prometheus metrics**: `http://localhost:9091`
- **Check container status**: `docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"`

## Architecture Overview

### Core Components
- **Frontend**: React 18 application with ReactFlow for workflow visualization (port 3020)
- **Backend**: FastAPI server with async support (port 8000)
- **Databases**: PostgreSQL (5434), Neo4j (7474), Redis (6379), Elasticsearch (9200)
- **Orchestration**: Camunda Platform 8.5 for BPMN workflow execution
- **Monitoring**: Grafana (3021) and Prometheus (9091)

### Key Architecture Patterns
- **Multi-database architecture**: PostgreSQL for workflows, Neo4j for relationships, Redis for pub/sub
- **Container orchestration**: All services run in Docker with network isolation
- **Agent-based coordination**: 25 specialized AI personas using LangChain/LangGraph
- **Workflow-driven**: YAML-defined workflows with 18 system workflows (wf0-wf17)

## Implementation Plan

The comprehensive implementation plan for this project is maintained at:
**`/home/davidarule/ai-persona-orchestrator/IMPLEMENTATION-PLAN.md`**

This living document contains:
- 150 sequential TODOs organized in 10 phases
- Detailed technical specifications
- Database schemas
- API designs
- Error handling strategies
- Current status tracking

### Active Plan Summary
- **Current TODO**: #1 - Add persona instance tables to database schema
- **Current Phase**: Phase 1 - Database Foundation (TODOs 1-10)
- **Key Decision**: Start with Software Architect persona as first complete implementation
- **Architecture**: Personas are abstract types that can be instantiated multiple times
- **Constraint**: Each persona instance works on only ONE project

### Memory System References
- Check memory for "ACTIVE_TODO" to see current task
- Check memory for "AI Persona Orchestrator Implementation Plan" for plan location
- Update IMPLEMENTATION-PLAN.md as tasks are completed

### Directory Structure
```
backend/
├── api/server.py           # FastAPI application entry point
├── agents/agent_factory.py # AI agent implementations and factory
├── orchestration/          # LangGraph coordination logic
└── requirements.txt        # Python dependencies

frontend/
├── src/App.js              # Main React application
├── src/WorkflowVisualizer.jsx # ReactFlow workflow visualization
└── package.json            # Node.js dependencies

workflows/
├── system/                 # 18 core DevOps workflows (wf0-wf17)
└── personas/               # 25 AI persona workflow definitions

monitoring/
├── grafana/dashboards/     # Pre-configured dashboards
└── prometheus/             # Metrics collection configuration
```

## Workflow System

### System Workflows (wf0-wf17)
The system includes 18 core workflows covering the complete DevOps lifecycle:
- **wf0**: Feature Development (master workflow)
- **wf1-wf2**: Bug fixes and hotfixes
- **wf3-wf8**: Git operations (branch, commit, PR, merge)
- **wf9-wf11**: Monitoring and rollback
- **wf12-wf17**: DevOps utilities and configuration

### Workflow YAML Structure
Workflows follow this pattern:
```yaml
metadata:
  id: unique-workflow-id
  name: Workflow Name
  type: master|core
  
inputs:
  - name: INPUT_NAME
    type: string|enum|boolean
    required: true

steps:
  - id: step-id
    action: execute-workflow|shell-command|git-operation
    
outputs:
  - name: OUTPUT_NAME
    value: ${steps.step-id.output}
```

### AI Personas
25 specialized agents in roles like Senior Developer, QA Engineer, Security Architect, etc. Each persona has its own workflow definition in `workflows/personas/`.

## Development Workflow

### Adding New Workflows
1. Create YAML file in `workflows/system/` or `workflows/personas/`
2. Run `python3 scripts/load_workflows.py` to load into database
3. Update agent factory if needed: `backend/agents/agent_factory.py`

### Testing Changes
1. Use health check script to verify all services are running
2. Test individual components with their respective commands
3. Run integration tests to verify end-to-end functionality

### Environment Configuration
- Copy `.env.example` to `.env` and configure required variables
- Key variables: Azure DevOps PAT, AI model API keys, database passwords
- All services use environment variables for configuration

## Technology Integration

### AI/LLM Integration
- Multi-model support: OpenAI GPT, Anthropic Claude, Google Gemini, Grok
- LangChain framework for LLM interactions
- LangGraph for agent coordination and workflow orchestration

### Azure DevOps Integration
- Uses azure-devops Python SDK for work item management
- PAT token authentication required
- Integrated with all 18 system workflows

### Real-time Features
- WebSocket connections for live workflow updates
- Redis pub/sub for agent status broadcasting
- ReactFlow for interactive workflow visualization

## Important Notes

- All services run in containers - avoid direct host installations
- Workflow definitions are stored in PostgreSQL and cached in Redis
- Neo4j stores workflow relationship graphs for optimization
- Camunda handles BPMN process execution with Elasticsearch for events
- The system is designed for production deployment with SSL/TLS support
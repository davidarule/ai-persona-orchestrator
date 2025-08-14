# AI Persona Orchestrator - Comprehensive Implementation Plan

## Document Version
- **Version**: 1.0.0
- **Last Updated**: 2025-01-14
- **Status**: ACTIVE IMPLEMENTATION PLAN
- **Next TODO**: #1 - Add persona instance tables to database schema

## Executive Summary

The AI Persona Orchestrator is a comprehensive visual workflow orchestration system that integrates AI personas with Azure DevOps. The system enables multiple AI agents to collaborate on software development tasks through Azure DevOps integration, with real-time monitoring and visual workflow management.

### Key Architectural Decisions

1. **Personas as Abstract Types**: The 25 personas (Software Architect, QA Engineer, etc.) are abstract types that can be instantiated multiple times. For example, you can create 3 Software Architect instances, each assigned to different projects.

2. **Instance Isolation**: Each persona instance works on only ONE project to avoid context confusion between projects.

3. **Hierarchical Orchestration**: 
   - LangGraph (Primary AI Orchestrator) → 
   - Camunda (BPMN Process Engine) → 
   - System Workflows (wf0-wf17) → 
   - Persona Workflows

4. **Azure DevOps Integration**: Personas act as actual team members in Azure DevOps, following the same processes as human users.

5. **Multi-Database Architecture**:
   - PostgreSQL: Primary data store (port 5434)
   - Neo4j: Graph relationships and optimization
   - Redis: Real-time pub/sub messaging
   - Elasticsearch: Search and analytics
   - Camunda/Zeebe: Workflow execution

## System Architecture Overview

### Core Components

1. **Frontend** (Port 3020)
   - React 18 with ReactFlow for workflow visualization
   - Real-time WebSocket updates
   - Dashboard for monitoring persona activities

2. **Backend API** (Port 8000)
   - FastAPI with async support
   - LangGraph orchestration
   - MCP server integration

3. **Persona System**
   - 25 Abstract Persona Types (defined in YAML)
   - Unlimited Persona Instances (assigned to projects)
   - Each instance has: project assignment, LLM config, spend limits

4. **Workflow System**
   - 18 System Workflows (wf0-wf17)
   - 25 Persona Workflow Types
   - YAML definitions as source of truth
   - BPMN generation for Camunda execution

5. **Communication System**
   - Redis pub/sub for real-time messaging
   - PostgreSQL for message persistence
   - Standardized PersonaMessage protocol
   - Token bucket workload balancing

6. **MCP Servers** (8 total)
   - Memory, File System, GitHub, PostgreSQL
   - Context7, Serena, Memory Bank, Nova
   - Discoverable capabilities
   - Permission based on workflows

### Key Design Principles

1. **Scalability**: Support for hundreds of concurrent persona instances
2. **Flexibility**: Multiple LLM providers with fallback chains
3. **Reliability**: Circuit breakers, retries, error boundaries
4. **Observability**: Comprehensive logging and monitoring
5. **Security**: JWT auth, encrypted PATs, HTTPS

## Implementation Approach

This plan follows a sequential implementation strategy with integrated testing:

1. **Foundation Phase**: Database schema, core infrastructure + comprehensive testing
2. **Core Systems Phase**: Persona management, workflow engine + comprehensive testing
3. **Integration Phase**: MCP servers, Azure DevOps + comprehensive testing
4. **Enhancement Phase**: Visualization, monitoring + comprehensive testing
5. **Completion Phase**: Remaining personas, E2E testing, deployment

Each phase includes:
- Implementation of core functionality
- Unit tests for all components
- Integration tests with real services
- E2E tests where applicable (no mocks, real data only)

The first persona to be fully implemented is the **Software Architect**, which will serve as the template for the remaining 24 personas.

## Testing Infrastructure

### Test Environment
- **Azure DevOps Project**: AI-Personas-Test-Sandbox-2 (https://data6.visualstudio.com/AI-Personas-Test-Sandbox-2)
- **13 Test Personas**: Already configured as team members in Azure DevOps
- **Real Services**: PostgreSQL (5434), Redis (6379), Neo4j (7687), Azure DevOps API

### Test Personas Available
1. **Steve Bot** (steve.bot) - System Architect
2. **Jordan Bot** (jordan.bot) - Backend Developer  
3. **Matt Bot** (matt.bot) - Frontend Developer
4. **Shaun Bot** (shaun.bot) - UI/UX Designer
5. **Kav Bot** (kav.bot) - Test Engineer
6. **Lachlan Bot** (lachlan.bot) - DevSecOps Engineer
7. **Dave Bot** (dave.bot) - Security Engineer
8. **Laureen Bot** (laureen.bot) - Technical Writer
9. **Ruley Bot** (ruley.bot) - Requirements Analyst
10. **Brumbie Bot** (brumbie.bot) - Project Manager
11. **Moby Bot** (moby.bot) - Mobile Developer
12. **Claude Bot** (claude.bot) - AI Integration
13. **Puck Bot** (puck.bot) - Developer

All personas use email pattern: {username}@insitec.com.au

---

## Database Schema Requirements

### Existing Tables (Already Created)
- orchestrator.workflow_status
- orchestrator.agent_status  
- orchestrator.workflow_definitions
- orchestrator.work_items

### New Tables Required

```sql
-- 1. Persona Instance Management
CREATE TABLE orchestrator.persona_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type_name VARCHAR(100) UNIQUE NOT NULL, -- e.g., 'software-architect'
    display_name VARCHAR(255) NOT NULL,      -- e.g., 'Software Architect'
    base_workflow_id VARCHAR(255),           -- Reference to persona workflow
    default_capabilities JSONB,              -- Default capabilities for this type
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE orchestrator.persona_instances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_name VARCHAR(255) NOT NULL,     -- e.g., 'Steve Bot - Project Alpha'
    persona_type_id UUID REFERENCES persona_types(id),
    
    -- Project Assignment (one project per instance)
    azure_devops_org VARCHAR(500),
    azure_devops_project VARCHAR(500),
    repository_name VARCHAR(500),
    
    -- LLM Configuration
    llm_providers JSONB,  -- Priority-ordered list with models
    spend_limit_daily DECIMAL(10,2),
    spend_limit_monthly DECIMAL(10,2),
    current_spend_daily DECIMAL(10,2) DEFAULT 0,
    current_spend_monthly DECIMAL(10,2) DEFAULT 0,
    
    -- Instance Configuration
    max_concurrent_tasks INTEGER DEFAULT 5,
    priority_level INTEGER DEFAULT 0,
    custom_settings JSONB,
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    last_activity TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(instance_name, azure_devops_project)
);

-- 2. MCP Server Registry
CREATE TABLE orchestrator.mcp_servers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_name VARCHAR(100) UNIQUE NOT NULL,
    server_type VARCHAR(50),
    connection_config JSONB,
    is_deployed BOOLEAN DEFAULT false,
    health_check_url VARCHAR(500),
    last_health_check TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE orchestrator.mcp_capabilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_id UUID REFERENCES mcp_servers(id),
    capability_name VARCHAR(255) NOT NULL,
    capability_type VARCHAR(100),
    description TEXT,
    parameters_schema JSONB,
    response_schema JSONB,
    rate_limit INTEGER,
    timeout_ms INTEGER DEFAULT 30000,
    is_available BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(server_id, capability_name)
);

CREATE TABLE orchestrator.persona_mcp_permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_instance_id UUID REFERENCES persona_instances(id),
    capability_id UUID REFERENCES mcp_capabilities(id),
    can_read BOOLEAN DEFAULT true,
    can_write BOOLEAN DEFAULT false,
    can_execute BOOLEAN DEFAULT true,
    custom_rate_limit INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(persona_instance_id, capability_id)
);

-- 3. RACI Matrix
CREATE TABLE orchestrator.raci_definitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id VARCHAR(100),
    phase VARCHAR(100),
    task_type VARCHAR(100),
    responsible JSONB DEFAULT '[]',
    accountable JSONB DEFAULT '[]',
    consulted JSONB DEFAULT '[]',
    informed JSONB DEFAULT '[]',
    min_approvals INTEGER DEFAULT 1,
    escalation_timeout INTEGER,
    auto_approve_conditions JSONB,
    veto_power JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 4. Persona Communication
CREATE TABLE orchestrator.persona_communications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id VARCHAR(255) UNIQUE NOT NULL,
    correlation_id VARCHAR(255),
    
    -- Participants
    sender_persona_id UUID REFERENCES persona_instances(id),
    recipient_persona_id UUID REFERENCES persona_instances(id),
    cc_personas JSONB DEFAULT '[]',
    
    -- Message Details
    workflow_execution_id UUID,
    message_type VARCHAR(50), -- handoff, consultation, escalation, inform
    priority VARCHAR(20),     -- critical, high, medium, low
    subject TEXT,
    
    -- Payload
    body JSONB,
    context JSONB,
    attachments JSONB DEFAULT '[]',
    
    -- Protocol
    requires_acknowledgment BOOLEAN DEFAULT false,
    acknowledgment_timeout INTEGER,
    requires_response BOOLEAN DEFAULT false,
    response_timeout INTEGER,
    
    -- Status Tracking
    status VARCHAR(50) DEFAULT 'sent',
    acknowledged_at TIMESTAMP,
    response JSONB,
    processed_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

-- 5. Workflow State Synchronization
CREATE TABLE orchestrator.workflow_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id VARCHAR(100),
    work_item_id VARCHAR(255),
    
    -- State Management
    langgraph_state JSONB,
    camunda_process_id VARCHAR(255),
    current_phase VARCHAR(100),
    sync_status VARCHAR(50),
    
    -- Execution Details
    started_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    status VARCHAR(50),
    error_details JSONB,
    
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE orchestrator.workflow_state_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id UUID REFERENCES workflow_executions(id),
    source VARCHAR(50), -- 'langgraph' or 'camunda'
    event_type VARCHAR(100),
    payload JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 6. Performance Indexes
CREATE INDEX idx_persona_instances_project ON orchestrator.persona_instances(azure_devops_project);
CREATE INDEX idx_persona_instances_type ON orchestrator.persona_instances(persona_type_id);
CREATE INDEX idx_persona_comm_workflow ON orchestrator.persona_communications(workflow_execution_id);
CREATE INDEX idx_persona_comm_status ON orchestrator.persona_communications(status);
CREATE INDEX idx_persona_comm_created ON orchestrator.persona_communications(created_at DESC);
CREATE INDEX idx_workflow_exec_status ON orchestrator.workflow_executions(status);
CREATE INDEX idx_workflow_exec_item ON orchestrator.workflow_executions(work_item_id);
CREATE INDEX idx_raci_workflow ON orchestrator.raci_definitions(workflow_id);

-- 7. Update Triggers
CREATE TRIGGER update_persona_instances_updated_at 
    BEFORE UPDATE ON orchestrator.persona_instances 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_raci_definitions_updated_at 
    BEFORE UPDATE ON orchestrator.raci_definitions 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_workflow_executions_updated_at 
    BEFORE UPDATE ON orchestrator.workflow_executions 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

---

## Sequential Implementation TODO List

### Phase 1: Database Foundation (TODOs 1-10)

**TODO 1**: Add persona instance tables to database schema
- Connect to PostgreSQL at port 5434
- Execute CREATE TABLE statements for: persona_types, persona_instances
- Verify tables created successfully
- Test with sample inserts

**TODO 2**: Add MCP server registry tables
- Execute CREATE TABLE for: mcp_servers, mcp_capabilities, persona_mcp_permissions
- Insert initial MCP server records (8 servers)
- Set all is_deployed to false initially

**TODO 3**: Add RACI and communication tables
- Execute CREATE TABLE for: raci_definitions, persona_communications
- Create workflow execution tables: workflow_executions, workflow_state_events
- Add all indexes for performance

**TODO 4**: Deploy all 25 persona workflows to database
- Run `python3 scripts/deploy_workflows.py` for persona workflows
- Verify each persona YAML loaded into workflow_definitions table
- Check that all 25 persona types are registered

**TODO 5**: Deploy all 18 system workflows to database
- Run deployment for system workflows (wf0-wf17)
- Verify workflow metadata correctly stored
- Test workflow retrieval from database

**TODO 6**: Populate persona_types table
- Insert all 25 persona types with correct type_name and display_name
- Link each to their base workflow YAML
- Set default capabilities based on role

**TODO 7**: Create database migration script
- Create scripts/migrations/001_persona_instances.sql
- Include rollback procedures
- Document migration process

**TODO 8**: Initialize RACI definitions from workflows
- Parse workflow YAML files to extract RACI patterns
- Insert base RACI definitions for feature development (wf0)
- Create script to generate remaining RACI entries

**TODO 9**: Set up database connection pooling
- Configure asyncpg pool in backend/api/server.py
- Set min_size=10, max_size=20 for production
- Add connection retry logic

**TODO 10**: Create database health check endpoint
- Add /api/health/database endpoint
- Check all critical tables accessible
- Return table counts and connection status

### Phase 1 Testing: Database Foundation Tests

**TODO 10a**: Create test infrastructure
- Set up tests/ directory structure
- Configure pytest with asyncio support
- Create base fixtures for database connections
- Add test dependencies to requirements.txt

**TODO 10b**: Unit tests for database components
- Test database configuration classes
- Test connection pool initialization
- Test query builders and utilities
- Test health check logic

**TODO 10c**: Integration tests for database layer
- Test real PostgreSQL connections and queries
- Test Redis operations
- Test Neo4j connections (if available)
- Test connection pool behavior under load

**TODO 10d**: E2E tests for database operations
- Test complete workflow from API to database
- Test concurrent database operations
- Test database failover and recovery
- Verify all migrations applied correctly

### Phase 2: Persona Instance Management (TODOs 11-25)

**TODO 11**: Create PersonaType model and repository
- Create backend/models/persona_type.py with Pydantic model
- Create backend/repositories/persona_repository.py
- Implement CRUD operations for persona types

**TODO 12**: Create PersonaInstance model
- Define PersonaInstance Pydantic model
- Include all fields: name, type, project assignment, LLM config
- Add validation for project uniqueness per instance

**TODO 13**: Build persona instance factory
- Create backend/services/persona_instance_factory.py
- Implement create_instance() method
- Validate project assignment and LLM configuration

**TODO 14**: Implement LLM provider configuration
- Create backend/models/llm_config.py
- Support priority-ordered list of providers
- Include model selection, temperature, max_tokens

**TODO 15**: Add spend tracking system
- Create backend/services/spend_tracker.py
- Track daily and monthly spend per instance
- Implement spend limit enforcement

**TODO 16**: Build persona instance API endpoints
- POST /api/personas/instances - Create new instance
- GET /api/personas/instances - List all instances
- GET /api/personas/instances/{id} - Get specific instance
- PUT /api/personas/instances/{id} - Update instance
- DELETE /api/personas/instances/{id} - Deactivate instance

**TODO 17**: Create project assignment validation
- Verify Azure DevOps org/project exists
- Check if persona has access to project
- Validate repository exists in project

**TODO 18**: Implement persona instance lifecycle
- Create activation/deactivation logic
- Track last_activity timestamp
- Implement instance cleanup on deactivation

**TODO 19**: Build LLM fallback chain
- Create backend/services/llm_chain.py
- Implement provider fallback logic
- Handle rate limits and errors gracefully

**TODO 20**: Add persona instance monitoring
- Track active instances per type
- Monitor task load per instance
- Create instance health metrics

**TODO 21**: Create instance configuration UI
- Add frontend form for creating instances
- Include project selector from Azure DevOps
- Add LLM provider configuration UI

**TODO 22**: Implement instance testing
- Create tests/test_persona_instances.py
- Test instance creation, assignment, limits
- Verify project isolation

**TODO 23**: Build instance state persistence
- Save instance state between restarts
- Implement state recovery on startup
- Handle interrupted workflows

**TODO 24**: Create instance audit logging
- Log all instance operations
- Track configuration changes
- Store in audit_log table

**TODO 25**: Complete Software Architect persona implementation
- Use Software Architect as first complete implementation
- Implement all workflow steps from YAML
- Test with real Azure DevOps project

### Phase 3: Workflow Engine Integration (TODOs 26-40)

**TODO 26**: Complete LangGraph orchestrator setup
- Finish backend/orchestration/langgraph_coordinator.py
- Implement WorkflowState management
- Add checkpointing with PostgreSQL

**TODO 27**: Create YAML to BPMN converter
- Build scripts/yaml_to_bpmn_converter.py
- Map YAML workflow steps to BPMN elements
- Generate BPMN XML for Camunda

**TODO 28**: Convert all 18 system workflows to BPMN
- Run converter on system workflows (wf0-wf17)
- Store BPMN files in workflows/bpmn/
- Validate BPMN with Camunda

**TODO 29**: Implement Zeebe client integration
- Create backend/services/zeebe_client.py
- Connect to Zeebe at port 26500
- Deploy BPMN workflows to Zeebe

**TODO 30**: Build LangGraph workflow nodes
- Implement nodes for each workflow phase
- Add decision routing logic
- Connect to persona execution

**TODO 31**: Create workflow state synchronization
- Implement state sync between LangGraph and Camunda
- Use workflow_state_events table
- Add event notifications via Redis

**TODO 32**: Build workflow execution API
- POST /api/workflow/execute - Start workflow
- GET /api/workflow/status/{id} - Get status
- POST /api/workflow/cancel/{id} - Cancel workflow
- GET /api/workflow/history/{work_item_id}

**TODO 33**: Implement workflow error handling
- Create WorkflowErrorBoundary class
- Add retry logic with exponential backoff
- Implement circuit breaker pattern

**TODO 34**: Add workflow timeout management
- Create TimeoutManager class
- Implement workflow-specific SLAs
- Add timeout escalation logic

**TODO 35**: Build workflow checkpointing
- Save workflow state at each phase
- Enable resume from checkpoint
- Handle partial failures

**TODO 36**: Create workflow monitoring
- Track execution times per phase
- Monitor success/failure rates
- Identify bottlenecks

**TODO 37**: Implement workflow routing
- Build intelligent routing based on RACI
- Route to available personas
- Handle workload balancing

**TODO 38**: Add workflow event streaming
- Stream events to frontend via WebSocket
- Update workflow visualization in real-time
- Store events for replay

**TODO 39**: Create workflow testing framework
- Build workflow test harness
- Create mock personas for testing
- Test all 18 system workflows

**TODO 40**: Implement workflow versioning
- Support multiple workflow versions
- Handle version migrations
- Maintain backward compatibility

### Phase 4: MCP Server Integration (TODOs 41-55)

**TODO 41**: Install MCP server npm packages
- Install @modelcontextprotocol/server-memory
- Install @modelcontextprotocol/server-filesystem
- Document installation process

**TODO 42**: Deploy Memory MCP server
- Configure and start Memory server
- Test basic store/retrieve operations
- Update mcp_servers table

**TODO 43**: Deploy File System MCP server
- Configure with workspace path
- Set permission boundaries
- Test file operations

**TODO 44**: Deploy GitHub MCP server
- Configure with GitHub credentials
- Set repository access permissions
- Test PR and issue operations

**TODO 45**: Deploy PostgreSQL MCP server
- Configure read-only access
- Set query permissions
- Test database queries

**TODO 46**: Deploy Context7 MCP server
- Install and configure Context7
- Set up documentation access
- Test context retrieval

**TODO 47**: Deploy Serena MCP server
- Install and configure Serena
- Set up code analysis capabilities
- Test semantic search

**TODO 48**: Deploy Memory Bank MCP server
- Configure persistent memory storage
- Set up memory hierarchies
- Test memory operations

**TODO 49**: Deploy Nova MCP server
- Configure advanced reasoning
- Set up constraint solving
- Test complex queries

**TODO 50**: Implement MCP capability discovery
- Create capability scanner for each server
- Store capabilities in database
- Build capability registry

**TODO 51**: Create MCP client adapter
- Build backend/services/mcp_client.py
- Implement server communication
- Add connection pooling

**TODO 52**: Build MCP permission system
- Map persona workflows to MCP capabilities
- Implement permission checks
- Add rate limiting per capability

**TODO 53**: Create MCP health monitoring
- Implement health checks for each server
- Monitor server availability
- Add automatic failover

**TODO 54**: Integrate HACS memory system
- Review HACS documentation (when provided)
- Implement HACS patterns
- Test with persona memories

**TODO 55**: Test MCP server integration
- Create integration tests
- Test each server individually
- Test cross-server operations

### Phase 5: Communication System (TODOs 56-70)

**TODO 56**: Create PersonaMessage model
- Implement backend/models/persona_message.py
- Define message types and priorities
- Add validation rules

**TODO 57**: Build PersonaMessenger service
- Create backend/communication/persona_messenger.py
- Implement hybrid Redis/PostgreSQL messaging
- Add message routing logic

**TODO 58**: Set up Redis pub/sub channels
- Configure channel structure
- Implement channel subscriptions
- Add message broadcasting

**TODO 59**: Create message persistence layer
- Store messages in PostgreSQL
- Implement message history
- Add message search

**TODO 60**: Build three-way handshake protocol
- Implement SYN/SYN-ACK/ACK pattern
- Add handshake timeout handling
- Create secure channel establishment

**TODO 61**: Implement token bucket algorithm
- Create PersonaScheduler class
- Add workload balancing logic
- Implement rate limiting per persona

**TODO 62**: Build message priority queues
- Set up priority channels in Redis
- Implement queue management
- Add priority-based routing

**TODO 63**: Create communication API endpoints
- POST /api/messages/send - Send message
- GET /api/messages/inbox/{persona_id}
- POST /api/messages/acknowledge/{message_id}
- GET /api/messages/history

**TODO 64**: Add message acknowledgment system
- Track acknowledgment status
- Implement timeout handling
- Add retry for unacknowledged messages

**TODO 65**: Build inter-persona protocols
- Define handoff protocol
- Create consultation workflow
- Implement escalation patterns

**TODO 66**: Create communication monitoring
- Track message flow metrics
- Monitor response times
- Identify communication bottlenecks

**TODO 67**: Implement message filtering
- Add spam/noise filtering
- Create relevance scoring
- Route based on content

**TODO 68**: Build communication testing
- Create message flow tests
- Test priority handling
- Verify acknowledgment system

**TODO 69**: Add communication visualization
- Show active conversations
- Display message flow diagram
- Track communication patterns

**TODO 70**: Create communication audit trail
- Log all messages
- Track routing decisions
- Store for compliance

### Phase 6: Azure DevOps Integration (TODOs 71-85)

**TODO 71**: Create Azure DevOps settings system
- Add organization URL configuration
- Store encrypted PAT tokens
- Support multiple organizations

**TODO 72**: Build Azure DevOps client service
- Create backend/services/azure_devops_client.py
- Implement connection management
- Add retry logic for API calls

**TODO 73**: Implement project discovery
- Download project list from organization
- Store project metadata
- Update project cache periodically

**TODO 74**: Create persona team member system
- Add personas as team members in projects
- Verify persona has project access
- Handle permission errors

**TODO 75**: Build work item synchronization
- Sync work items from Azure DevOps
- Update local work_items table
- Track work item changes

**TODO 76**: Implement webhook endpoints
- POST /api/webhooks/azure-devops/work-item
- POST /api/webhooks/azure-devops/pull-request
- POST /api/webhooks/azure-devops/build
- Add webhook signature validation

**TODO 77**: Create webhook event processors
- Process work item events
- Handle PR events
- React to build notifications

**TODO 78**: Build pull request automation
- Create PRs via API
- Add reviewers based on RACI
- Update PR status

**TODO 79**: Implement pipeline integration
- Trigger pipelines from workflows
- Monitor pipeline status
- Handle pipeline failures

**TODO 80**: Add work item state management
- Update work item states
- Add comments to work items
- Link commits to work items

**TODO 81**: Create Azure DevOps repository integration
- Clone repositories for personas
- Create branches programmatically
- Commit and push changes

**TODO 82**: Build Azure DevOps monitoring
- Track API usage and rate limits
- Monitor webhook delivery
- Alert on integration failures

**TODO 83**: Implement Azure DevOps caching
- Cache project and team data
- Cache work item metadata
- Implement cache invalidation

**TODO 84**: Add Azure DevOps error handling
- Handle API rate limits
- Manage authentication failures
- Implement graceful degradation

**TODO 85**: Test Azure DevOps integration
- Test with data6 sandbox
- Verify all API operations
- Test webhook processing

### Phase 7: RACI Implementation (TODOs 86-95)

**TODO 86**: Generate RACI from workflows
- Create scripts/generate_raci.py
- Parse all workflow YAML files
- Extract responsibility patterns

**TODO 87**: Populate RACI definitions
- Insert generated RACI entries
- Set up approval chains
- Define escalation paths

**TODO 88**: Build RACI decision engine
- Create backend/services/raci_engine.py
- Implement responsibility routing
- Add approval logic

**TODO 89**: Create RACI-based routing
- Route tasks based on RACI matrix
- Find responsible personas
- Handle unavailable personas

**TODO 90**: Implement approval workflows
- Build approval request system
- Track approval status
- Implement auto-approval rules

**TODO 91**: Add escalation mechanisms
- Implement timeout-based escalation
- Create escalation chains
- Notify management personas

**TODO 92**: Build RACI visualization
- Create RACI matrix view in frontend
- Show current assignments
- Display approval chains

**TODO 93**: Implement veto power logic
- Check veto permissions
- Handle veto decisions
- Provide veto justification

**TODO 94**: Create RACI testing
- Test routing decisions
- Verify approval chains
- Test escalation paths

**TODO 95**: Add RACI audit logging
- Log all RACI decisions
- Track approval history
- Store for compliance

### Phase 8: Frontend Enhancement (TODOs 96-110)

**TODO 96**: Enhance WorkflowVisualizer component
- Add real-time updates via WebSocket
- Implement zoom and pan controls
- Add workflow step details

**TODO 97**: Create workflow node components
- Build custom ReactFlow nodes
- Add status indicators
- Show persona assignments

**TODO 98**: Implement workflow timeline view
- Show execution timeline
- Display phase durations
- Highlight bottlenecks

**TODO 99**: Build persona activity dashboard
- Show all active persona instances
- Display current tasks
- Monitor workload

**TODO 100**: Create workflow builder UI
- Drag-and-drop workflow creation
- YAML export functionality
- Workflow validation

**TODO 101**: Add real-time notifications
- WebSocket notification system
- Desktop notifications
- Priority-based alerts

**TODO 102**: Build persona instance manager UI
- List all persona instances
- Create/edit/delete instances
- Configure LLM providers

**TODO 103**: Create communication viewer
- Show active conversations
- Display message threads
- Filter by persona or workflow

**TODO 104**: Implement RACI matrix editor
- Visual RACI editing
- Drag-drop assignments
- Preview approval chains

**TODO 105**: Add monitoring dashboards
- Workflow performance metrics
- Persona utilization charts
- System health indicators

**TODO 106**: Create audit log viewer
- Search and filter logs
- Export capabilities
- Compliance reports

**TODO 107**: Build settings management UI
- Azure DevOps configuration
- LLM provider settings
- System preferences

**TODO 108**: Add dark mode support
- Theme switching
- Persist user preference
- Consistent styling

**TODO 109**: Implement responsive design
- Mobile-friendly layouts
- Tablet optimization
- Desktop full features

**TODO 110**: Create help system
- In-app documentation
- Tooltips and guides
- Video tutorials

### Phase 9: Security & Performance (TODOs 111-125)

**TODO 111**: Implement JWT authentication
- Set up JWT token generation
- Add token validation middleware
- Implement refresh tokens

**TODO 112**: Add HTTPS configuration
- Configure SSL certificates
- Force HTTPS redirect
- Update CORS settings

**TODO 113**: Create API rate limiting
- Implement per-endpoint limits
- Add per-user rate limiting
- Return proper headers

**TODO 114**: Build secret rotation system
- Rotate API keys periodically
- Update PAT tokens
- Notify on expiration

**TODO 115**: Add input validation
- Validate all API inputs
- Prevent SQL injection
- Sanitize user data

**TODO 116**: Implement audit logging
- Log all API calls
- Track data changes
- Store securely

**TODO 117**: Create performance monitoring
- Add APM instrumentation
- Track response times
- Monitor resource usage

**TODO 118**: Optimize database queries
- Add query analysis
- Create missing indexes
- Implement query caching

**TODO 119**: Build caching layer
- Redis caching strategy
- Cache invalidation logic
- Monitor cache hit rates

**TODO 120**: Implement connection pooling
- Database connection pools
- MCP server connection pools
- Azure DevOps client pools

**TODO 121**: Add load testing
- Create load test scenarios
- Test with 200+ personas
- Identify bottlenecks

**TODO 122**: Build auto-scaling logic
- Monitor resource usage
- Scale persona instances
- Balance workload

**TODO 123**: Create backup automation
- Daily database backups
- Configuration backups
- Test restore process

**TODO 124**: Implement monitoring alerts
- Set up Prometheus alerts
- Configure notifications
- Create runbooks

**TODO 125**: Add security scanning
- Dependency vulnerability scanning
- Code security analysis
- Regular penetration testing

### Phase 10: Remaining Personas & Testing (TODOs 126-150)

**TODO 126**: Implement Backend Developer persona
- Use Software Architect as template
- Adapt for backend-specific tasks
- Test with real project

**TODO 127**: Implement Frontend Developer persona
- Focus on UI/UX tasks
- Add frontend-specific tools
- Test React/Angular projects

**TODO 128**: Implement QA Test Engineer persona
- Add testing workflows
- Integrate test frameworks
- Automate test execution

**TODO 129**: Implement DevSecOps Engineer persona
- Security-focused workflows
- CI/CD integration
- Infrastructure automation

**TODO 130**: Implement Product Owner persona
- Requirements management
- Stakeholder communication
- Priority decisions

**TODO 131-149**: Implement remaining 19 personas
- One TODO per remaining persona
- Follow same pattern as Software Architect
- Test each thoroughly

**TODO 150**: Complete system integration testing
- Test all personas together
- Verify inter-persona communication
- Full workflow execution tests

---

## Technical Specifications

### API Design

```python
# Persona Instance API
POST   /api/personas/types              # List persona types
POST   /api/personas/instances          # Create instance
GET    /api/personas/instances          # List instances
GET    /api/personas/instances/{id}     # Get instance
PUT    /api/personas/instances/{id}     # Update instance
DELETE /api/personas/instances/{id}     # Deactivate instance
POST   /api/personas/instances/{id}/assign  # Assign to project

# Workflow API
POST   /api/workflows/execute           # Start workflow
GET    /api/workflows/status/{id}       # Get status
POST   /api/workflows/cancel/{id}       # Cancel workflow
GET    /api/workflows/history           # Get history
WS     /ws/workflow-updates            # Real-time updates

# Communication API
POST   /api/messages/send              # Send message
GET    /api/messages/inbox/{persona_id} # Get inbox
POST   /api/messages/acknowledge/{id}   # Acknowledge
GET    /api/messages/history           # Message history

# Azure DevOps Webhooks
POST   /api/webhooks/azure-devops/work-item
POST   /api/webhooks/azure-devops/pull-request
POST   /api/webhooks/azure-devops/build
```

### Message Format

```python
class PersonaMessage(BaseModel):
    message_id: str
    correlation_id: str
    workflow_execution_id: str
    
    sender: Dict[str, str]      # {id, type, name}
    recipient: Dict[str, str]   # {id, type, name}
    cc: List[Dict[str, str]]
    
    communication_type: CommunicationType
    priority: CommunicationPriority
    subject: str
    
    body: Dict[str, Any]
    context: Dict[str, Any]
    attachments: List[Dict]
    
    requires_acknowledgment: bool
    acknowledgment_timeout: Optional[int]
    requires_response: bool
    response_timeout: Optional[int]
    
    created_at: datetime
    expires_at: Optional[datetime]
```

### Error Handling Strategy

```python
class ErrorHandler:
    severity_levels = {
        CRITICAL: "System failure, immediate intervention",
        HIGH: "Workflow blocked, escalation needed",
        MEDIUM: "Recoverable with retry",
        LOW: "Logged but continues"
    }
    
    error_strategies = {
        ("system", "database_connection"): {
            "severity": CRITICAL,
            "retry": True,
            "max_retries": 3,
            "escalate": True,
            "fallback": "use_cache"
        },
        ("workflow", "step_failure"): {
            "severity": HIGH,
            "retry": True,
            "rollback": True,
            "preserve_state": True
        }
    }
```

### Workflow Execution Strategy

```python
# Synchronous workflows (time-critical)
SYNC_WORKFLOWS = ['wf2-hotfix', 'wf11-rollback']

# Asynchronous workflows (long-running)
ASYNC_WORKFLOWS = ['wf0-feature-development', 'wf1-bug-fix']

# Workflow timeouts
WORKFLOW_TIMEOUTS = {
    'wf0-feature-development': {
        'global_timeout': 5 * 24 * 3600,  # 5 days
        'phase_timeouts': {
            'development': 3 * 24 * 3600,
            'testing': 24 * 3600,
            'review': 12 * 3600
        }
    },
    'wf2-hotfix': {
        'global_timeout': 4 * 3600,  # 4 hours
        'hard_limit': True,
        'auto_rollback': True
    }
}
```

### Redis Channel Structure

```python
REDIS_CHANNELS = {
    'persona:{persona_id}': 'Direct persona messages',
    'workflow:{execution_id}': 'Workflow-specific events',
    'priority:high': 'High-priority queue',
    'priority:medium': 'Medium-priority queue',
    'priority:low': 'Low-priority queue',
    'broadcast:all': 'System-wide announcements',
    'heartbeat:{persona_id}': 'Persona health checks'
}
```

---

## Living Document Notes

This implementation plan is a living document that will be updated as the project progresses. Changes will be tracked in the following locations:

1. **IMPLEMENTATION-PLAN.md** - This document (source of truth)
2. **Memory System** - ACTIVE_PLAN and ACTIVE_TODO entities
3. **CLAUDE.md** - Reference to this plan location

To update the plan:
1. Edit this document with new information
2. Update memory entities to reflect changes
3. Mark completed TODOs with ✅
4. Add new TODOs as discovered
5. Update technical specifications as needed

Current Status: **TODO 11** - Create PersonaType model and repository

## Progress Update (2025-01-14)

### Completed TODOs (Phase 1: Database Foundation)
- ✅ **TODO 1**: Add persona instance tables to database schema
  - Created persona_types, persona_instances tables
  - Created MCP server registry tables
  - Added all indexes and triggers
- ✅ **TODO 2**: Add MCP server registry tables  
  - Inserted all 8 MCP servers (Memory, File System, GitHub, etc.)
  - Added initial capabilities for some servers
- ✅ **TODO 3**: Add RACI and communication tables
  - Created raci_definitions, persona_communications
  - Created workflow_executions, workflow_state_events
- ✅ **TODO 4**: Deploy all 25 persona workflows to database
  - Fixed YAML syntax errors in 2 workflows
  - All 25 persona workflows successfully deployed
- ✅ **TODO 5**: Deploy all 18 system workflows to database
  - All system workflows (wf0-wf17) deployed
- ✅ **TODO 6**: Populate persona_types table
  - All 25 persona types with default capabilities
- ✅ **TODO 7**: Create database migration script
  - Created 3 migration scripts in scripts/migrations/
- ⏸️ **TODO 8**: Initialize RACI definitions from workflows (DEFERRED)
  - Deferred until after persona implementation
  - Created extraction scripts for future use
- ✅ **TODO 9**: Set up database connection pooling
  - Created database configuration module (backend/config/database.py)
  - Created database service layer (backend/services/database.py)
  - Implemented connection pooling for PostgreSQL, Redis, Neo4j
  - Added retry logic and health monitoring
- ✅ **TODO 10**: Create database health check endpoint
  - Added /api/health/database endpoint
  - Added /api/health/detailed endpoint
  - Monitors all database connections and pool status

### Completed TODOs (Phase 1 Testing)
- ✅ **TODO 10a**: Create test infrastructure
  - Set up tests/ directory structure with unit/integration/e2e
  - Configured pytest with asyncio support
  - Created base fixtures and conftest.py
  - Added test dependencies to requirements.txt
- ✅ **TODO 10b**: Unit tests for database components
  - Created 27 unit tests covering all database components
  - Test database configuration, connection pools, query builders
  - Test health check logic
- ✅ **TODO 10c**: Integration tests for database layer
  - Created 13 integration tests with real databases
  - Test PostgreSQL, Redis, Neo4j connections
  - Test connection pool behavior under load
- ✅ **TODO 10d**: E2E tests for database operations
  - Created 6 E2E tests from API to database
  - Test concurrent operations and failover
  - All 46 tests passing

### Additional Completed Work (Phase 1 Testing Extensions)
- ✅ Create test infrastructure and update documentation
  - Added comprehensive testing section to README.md
  - Created test personas in memory system
- ✅ Add test personas to memory system
  - Added all 13 test personas from AI-Personas-Test-Sandbox-2
- ✅ Create comprehensive tests for completed work (TODOs 1-10)
  - All database foundation work fully tested
- ✅ Create test dashboard and reporting infrastructure
  - Static dashboard at http://localhost:8090/test_dashboard/
  - HTML test reports with coverage
- ✅ Fix failing integration and E2E tests
  - Fixed all event loop issues
  - Fixed httpx client initialization
  - All 46 tests passing
- ✅ Create dynamic test dashboard with live updates and controls
  - Dynamic dashboard at http://localhost:8090/dynamic
  - WebSocket-based real-time test execution
  - Live log streaming and test controls
  - Fixed WebSocket handler compatibility issue

---

#!/bin/bash
#
# Start both test dashboard services
#

echo "Starting AI Persona Orchestrator Test Services..."
echo "============================================="

# Kill any existing processes
echo "Stopping any existing services..."
pkill -f "test_dashboard_server.py" 2>/dev/null
pkill -f "test_runner_service.py" 2>/dev/null
sleep 1

# Start the test runner WebSocket service
echo "Starting Test Runner Service (WebSocket on port 8765)..."
python3.11 scripts/test_runner_service.py > logs/test_runner.log 2>&1 &
TEST_RUNNER_PID=$!

# Give it a moment to start
sleep 2

# Start the dashboard HTTP server
echo "Starting Dashboard HTTP Server (port 8090)..."
python3.11 scripts/test_dashboard_server.py 8090 > logs/dashboard_server.log 2>&1 &
DASHBOARD_PID=$!

# Give it a moment to start
sleep 1

echo ""
echo "Services started successfully!"
echo "=============================="
echo ""
echo "Test Runner Service PID: $TEST_RUNNER_PID"
echo "Dashboard Server PID: $DASHBOARD_PID"
echo ""
echo "Access the dashboards at:"
echo "  - Landing Page: http://localhost:8090/"
echo "  - Static Dashboard: http://localhost:8090/test_dashboard/"
echo "  - Dynamic Dashboard: http://localhost:8090/dynamic"
echo ""
echo "To stop services, run: pkill -f test_dashboard_server.py && pkill -f test_runner_service.py"
echo ""
echo "Logs are available at:"
echo "  - logs/test_runner.log"
echo "  - logs/dashboard_server.log"
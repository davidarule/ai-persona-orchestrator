import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import WorkflowVisualizer from './WorkflowVisualizer';
import { AppBar, Toolbar, Typography, Container, Box, Button, Paper } from '@mui/material';
import axios from 'axios';
import './App.css';

function App() {
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [workflowStats, setWorkflowStats] = useState({
    active: 0,
    completed: 0,
    failed: 0
  });

  useEffect(() => {
    // Check backend connection
    checkBackendConnection();
    const interval = setInterval(checkBackendConnection, 30000); // Check every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const checkBackendConnection = async () => {
    try {
      const response = await axios.get('/api/health');
      if (response.data.status === 'healthy') {
        setConnectionStatus('connected');
      }
    } catch (error) {
      console.error('Backend connection error:', error);
      setConnectionStatus('disconnected');
    }
  };

  return (
    <Router>
      <Box sx={{ flexGrow: 1 }}>
        <AppBar position="static">
          <Toolbar>
            <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
              AI Persona Orchestrator
            </Typography>
            <Button color="inherit" component={Link} to="/">Dashboard</Button>
            <Button color="inherit" component={Link} to="/workflows">Workflows</Button>
            <Button color="inherit" component={Link} to="/agents">Agents</Button>
            <Box sx={{ ml: 2, px: 2, py: 0.5, bgcolor: connectionStatus === 'connected' ? 'success.main' : 'error.main', borderRadius: 1 }}>
              <Typography variant="caption">
                {connectionStatus === 'connected' ? 'Connected' : 'Disconnected'}
              </Typography>
            </Box>
          </Toolbar>
        </AppBar>

        <Container maxWidth="xl" sx={{ mt: 4 }}>
          <Routes>
            <Route path="/" element={<Dashboard stats={workflowStats} />} />
            <Route path="/workflows" element={<WorkflowVisualizer />} />
            <Route path="/agents" element={<AgentMonitor />} />
          </Routes>
        </Container>
      </Box>
    </Router>
  );
}

function Dashboard({ stats }) {
  return (
    <Box>
      <Typography variant="h4" gutterBottom>Dashboard</Typography>
      <Box sx={{ display: 'flex', gap: 2, mt: 3 }}>
        <Paper sx={{ p: 3, flex: 1 }}>
          <Typography variant="h6">Active Workflows</Typography>
          <Typography variant="h3">{stats.active}</Typography>
        </Paper>
        <Paper sx={{ p: 3, flex: 1 }}>
          <Typography variant="h6">Completed</Typography>
          <Typography variant="h3" color="success.main">{stats.completed}</Typography>
        </Paper>
        <Paper sx={{ p: 3, flex: 1 }}>
          <Typography variant="h6">Failed</Typography>
          <Typography variant="h3" color="error.main">{stats.failed}</Typography>
        </Paper>
      </Box>
    </Box>
  );
}

function AgentMonitor() {
  const [agents, setAgents] = useState([]);

  useEffect(() => {
    // TODO: Fetch agent status from backend
    setAgents([
      { name: 'Senior Developer', status: 'idle', lastTask: 'Feature-123' },
      { name: 'Code Reviewer', status: 'busy', lastTask: 'PR-456' },
      { name: 'QA Agent', status: 'idle', lastTask: 'Test-789' }
    ]);
  }, []);

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Agent Monitor</Typography>
      <Box sx={{ mt: 3 }}>
        {agents.map((agent, index) => (
          <Paper key={index} sx={{ p: 2, mb: 2 }}>
            <Typography variant="h6">{agent.name}</Typography>
            <Typography>Status: {agent.status}</Typography>
            <Typography variant="caption">Last Task: {agent.lastTask}</Typography>
          </Paper>
        ))}
      </Box>
    </Box>
  );
}

export default App;

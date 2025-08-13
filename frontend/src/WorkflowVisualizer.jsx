import React, { useEffect, useState, useCallback } from 'react';
import ReactFlow, {
  useNodesState,
  useEdgesState,
  addEdge,
  MiniMap,
  Controls,
  Background,
  Handle,
  Position,
} from 'reactflow';
import 'reactflow/dist/style.css';

const statusColors = {
  completed: '#2ECC71',
  'in-progress': '#3498DB',
  warning: '#F39C12',
  error: '#E74C3C',
  waiting: '#95A5A6',
  blocked: '#C0392B',
  stopped: '#2C3E50'
};

const AgentNode = ({ data }) => {
  const borderColor = statusColors[data.status] || statusColors.waiting;
  
  return (
    <div style={{
      padding: 10,
      borderRadius: 5,
      border: `3px solid ${borderColor}`,
      background: 'white',
      minWidth: 150
    }}>
      <Handle type="target" position={Position.Top} />
      <div>
        <strong>{data.label}</strong>
        <div style={{ fontSize: '0.8em', color: '#666' }}>
          {data.agentName}
        </div>
        <div style={{ fontSize: '0.7em', marginTop: 5 }}>
          Status: {data.status}
        </div>
        {data.workItemId && (
          <div style={{ fontSize: '0.7em' }}>
            WI: {data.workItemId}
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
};

const nodeTypes = {
  agentNode: AgentNode
};

function WorkflowVisualizer() {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [ws, setWs] = useState(null);

  useEffect(() => {
    // Connect to WebSocket for real-time updates
    const websocket = new WebSocket('wss://localhost:8085/workflow-updates');
    
    websocket.onmessage = (event) => {
      const update = JSON.parse(event.data);
      updateNodeStatus(update);
    };
    
    setWs(websocket);
    
    // Load initial workflow structure
    loadWorkflowStructure();
    
    return () => {
      websocket.close();
    };
  }, []);

  const updateNodeStatus = (update) => {
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id === update.nodeId) {
          return {
            ...node,
            data: {
              ...node.data,
              status: update.status,
              workItemId: update.workItemId,
              timestamp: update.timestamp
            }
          };
        }
        return node;
      })
    );
  };

  const loadWorkflowStructure = async () => {
    const response = await fetch('/api/workflow/structure');
    const structure = await response.json();
    
    // Convert workflow structure to React Flow nodes and edges
    const flowNodes = structure.nodes.map((node, index) => ({
      id: node.id,
      type: 'agentNode',
      position: { x: node.x || index * 200, y: node.y || Math.floor(index / 4) * 150 },
      data: {
        label: node.label,
        agentName: node.agentName,
        status: node.status || 'waiting',
        workItemId: node.workItemId
      }
    }));
    
    const flowEdges = structure.edges.map((edge) => ({
      id: `${edge.source}-${edge.target}`,
      source: edge.source,
      target: edge.target,
      animated: edge.animated || false,
      style: { stroke: edge.condition ? '#F39C12' : '#95A5A6' }
    }));
    
    setNodes(flowNodes);
    setEdges(flowEdges);
  };

  return (
    <div style={{ width: '100%', height: '100vh' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
      >
        <MiniMap />
        <Controls />
        <Background />
      </ReactFlow>
      <StatusLegend />
    </div>
  );
}

const StatusLegend = () => (
  <div style={{
    position: 'absolute',
    bottom: 20,
    left: 20,
    background: 'white',
    padding: 10,
    borderRadius: 5,
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
  }}>
    <strong>Status Legend:</strong>
    {Object.entries(statusColors).map(([status, color]) => (
      <div key={status} style={{ display: 'flex', alignItems: 'center', marginTop: 5 }}>
        <div style={{
          width: 20,
          height: 20,
          backgroundColor: color,
          marginRight: 10,
          borderRadius: 3
        }} />
        <span>{status}</span>
      </div>
    ))}
  </div>
);

export default WorkflowVisualizer;
import asyncio
import json
from typing import Dict, Any, List
from mcp import Server, Resource, Tool
from mcp.server.stdio import stdio_server

class MCPServerManager:
    def __init__(self):
        self.servers = {}
        self._initialize_servers()
    
    def _initialize_servers(self):
        """Initialize all MCP servers"""
        server_configs = {
            'memory': {
                'command': 'npx',
                'args': ['-y', '@modelcontextprotocol/server-memory']
            },
            'filesystem': {
                'command': 'npx',
                'args': ['-y', '@modelcontextprotocol/server-filesystem', '/workspace']
            },
            'context7': {
                'command': 'context7-server',
                'args': ['--port', '5001']
            },
            'serena': {
                'command': 'serena-server',
                'args': ['--config', '/config/serena.json']
            },
            'nova': {
                'command': 'nova-server',
                'args': []
            },
            'memory-bank': {
                'command': 'memory-bank-server',
                'args': ['--db', '/data/memory-bank.db']
            }
        }
        
        for name, config in server_configs.items():
            self.servers[name] = self._start_server(name, config)
    
    async def _start_server(self, name: str, config: Dict[str, Any]):
        """Start an MCP server subprocess"""
        process = await asyncio.create_subprocess_exec(
            config['command'],
            *config['args'],
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        return {
            'name': name,
            'process': process,
            'config': config
        }
    
    async def query_server(self, server_name: str, query: Dict[str, Any]) -> Any:
        """Query an MCP server"""
        if server_name not in self.servers:
            raise ValueError(f"Server {server_name} not found")
        
        server = self.servers[server_name]
        process = server['process']
        
        # Send query to server
        query_json = json.dumps(query) + '\n'
        process.stdin.write(query_json.encode())
        await process.stdin.drain()
        
        # Read response
        response = await process.stdout.readline()
        return json.loads(response.decode())
#!/usr/bin/python3.11
"""
Test Runner Service with WebSocket support for real-time updates
"""

import asyncio
import websockets
import json
import subprocess
import datetime
import os
import sys
from pathlib import Path
import threading
import queue
import time
import xml.etree.ElementTree as ET

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

class TestRunner:
    """Manages test execution with real-time output streaming"""
    
    def __init__(self):
        self.process = None
        self.output_queue = queue.Queue()
        self.is_running = False
        self.start_time = None
        self.test_stats = {
            "status": "idle",
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "errors": 0,
            "duration": 0,
            "coverage": 0
        }
        
    def start_tests(self, test_type="all"):
        """Start test execution"""
        if self.is_running:
            return False, "Tests already running"
            
        self.is_running = True
        self.start_time = time.time()
        self.test_stats["status"] = "running"
        
        # Prepare test command
        cmd = [
            sys.executable,
            "-m", "pytest",
            "tests/",
            "-v",
            "--tb=short",
            "--color=yes",
            "--cov=backend",
            "--cov-report=term",
            "--cov-report=json:test_reports/latest_coverage.json",
            "--junit-xml=test_reports/latest_junit.xml"
        ]
        
        # Add test type filter
        if test_type == "unit":
            cmd.extend(["tests/unit"])
        elif test_type == "integration":
            cmd.extend(["tests/integration", "-m", "integration"])
        elif test_type == "e2e":
            cmd.extend(["tests/e2e", "-m", "e2e"])
            
        # Set environment
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{Path.cwd()}:{Path.cwd()}/backend"
        
        # Load .env file
        if Path(".env").exists():
            with open(".env") as f:
                for line in f:
                    if line.strip() and not line.startswith("#"):
                        key, value = line.strip().split("=", 1)
                        env[key] = value.strip("'\"")
        
        # Start process
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
            env=env
        )
        
        # Start output reader thread
        threading.Thread(target=self._read_output, daemon=True).start()
        
        return True, "Tests started"
    
    def _read_output(self):
        """Read process output and queue it"""
        try:
            for line in iter(self.process.stdout.readline, ''):
                if line:
                    self.output_queue.put({
                        "type": "log",
                        "data": line.rstrip(),
                        "timestamp": datetime.datetime.now().isoformat()
                    })
                    
                    # Parse test progress
                    self._parse_progress(line)
                    
            self.process.wait()
            
            # Parse final results
            self._parse_final_results()
            
            self.is_running = False
            self.test_stats["status"] = "completed"
            self.test_stats["duration"] = int(time.time() - self.start_time)
            
            self.output_queue.put({
                "type": "complete",
                "data": self.test_stats,
                "timestamp": datetime.datetime.now().isoformat()
            })
            
        except Exception as e:
            self.output_queue.put({
                "type": "error",
                "data": str(e),
                "timestamp": datetime.datetime.now().isoformat()
            })
            self.is_running = False
            self.test_stats["status"] = "error"
    
    def _parse_progress(self, line):
        """Parse test progress from output"""
        # Parse pytest progress indicators
        if " PASSED " in line:
            self.test_stats["passed"] += 1
            self.test_stats["total"] += 1
        elif " FAILED " in line:
            self.test_stats["failed"] += 1
            self.test_stats["total"] += 1
        elif " SKIPPED " in line:
            self.test_stats["skipped"] += 1
            self.test_stats["total"] += 1
        elif " ERROR " in line:
            self.test_stats["errors"] += 1
            self.test_stats["total"] += 1
            
        # Update progress
        self.output_queue.put({
            "type": "progress",
            "data": self.test_stats,
            "timestamp": datetime.datetime.now().isoformat()
        })
    
    def _parse_final_results(self):
        """Parse final test results from junit.xml"""
        try:
            junit_file = Path("test_reports/latest_junit.xml")
            if junit_file.exists():
                tree = ET.parse(junit_file)
                root = tree.getroot()
                
                # Parse test suite results
                testsuite = root.find("testsuite")
                if testsuite is not None:
                    self.test_stats["total"] = int(testsuite.get("tests", 0))
                    self.test_stats["failed"] = int(testsuite.get("failures", 0))
                    self.test_stats["errors"] = int(testsuite.get("errors", 0))
                    self.test_stats["skipped"] = int(testsuite.get("skipped", 0))
                    self.test_stats["passed"] = (
                        self.test_stats["total"] - 
                        self.test_stats["failed"] - 
                        self.test_stats["errors"] - 
                        self.test_stats["skipped"]
                    )
            
            # Parse coverage
            coverage_file = Path("test_reports/latest_coverage.json")
            if coverage_file.exists():
                with open(coverage_file) as f:
                    coverage_data = json.load(f)
                    if "totals" in coverage_data:
                        self.test_stats["coverage"] = round(
                            coverage_data["totals"].get("percent_covered", 0), 1
                        )
                        
        except Exception as e:
            print(f"Error parsing results: {e}")
    
    def stop_tests(self):
        """Stop running tests"""
        if self.process and self.is_running:
            self.process.terminate()
            self.is_running = False
            self.test_stats["status"] = "stopped"
            return True, "Tests stopped"
        return False, "No tests running"
    
    def get_output(self, timeout=0.1):
        """Get queued output"""
        outputs = []
        try:
            while True:
                output = self.output_queue.get(timeout=timeout)
                outputs.append(output)
        except queue.Empty:
            pass
        return outputs


# Global test runner instance
test_runner = TestRunner()


async def websocket_handler(websocket):
    """Handle WebSocket connections"""
    print(f"New WebSocket connection from {websocket.remote_address}")
    
    try:
        # Send initial status
        await websocket.send(json.dumps({
            "type": "status",
            "data": test_runner.test_stats,
            "timestamp": datetime.datetime.now().isoformat()
        }))
        
        # Handle messages
        async for message in websocket:
            try:
                data = json.loads(message)
                command = data.get("command")
                
                if command == "start":
                    test_type = data.get("test_type", "all")
                    success, msg = test_runner.start_tests(test_type)
                    await websocket.send(json.dumps({
                        "type": "command_response",
                        "command": "start",
                        "success": success,
                        "message": msg,
                        "timestamp": datetime.datetime.now().isoformat()
                    }))
                    
                    # Start sending output
                    if success:
                        asyncio.create_task(send_output(websocket))
                        
                elif command == "stop":
                    success, msg = test_runner.stop_tests()
                    await websocket.send(json.dumps({
                        "type": "command_response",
                        "command": "stop",
                        "success": success,
                        "message": msg,
                        "timestamp": datetime.datetime.now().isoformat()
                    }))
                    
                elif command == "status":
                    await websocket.send(json.dumps({
                        "type": "status",
                        "data": test_runner.test_stats,
                        "timestamp": datetime.datetime.now().isoformat()
                    }))
                    
            except json.JSONDecodeError:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Invalid JSON",
                    "timestamp": datetime.datetime.now().isoformat()
                }))
                
    except websockets.exceptions.ConnectionClosed:
        print(f"WebSocket connection closed from {websocket.remote_address}")
    except Exception as e:
        print(f"WebSocket error: {e}")


async def send_output(websocket):
    """Send test output to WebSocket client"""
    while test_runner.is_running or not test_runner.output_queue.empty():
        outputs = test_runner.get_output(timeout=0.1)
        for output in outputs:
            try:
                await websocket.send(json.dumps(output))
            except websockets.exceptions.ConnectionClosed:
                return
        await asyncio.sleep(0.1)


async def main():
    """Start WebSocket server"""
    print("Starting Test Runner WebSocket Server on ws://localhost:8765")
    async with websockets.serve(websocket_handler, "localhost", 8765):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())
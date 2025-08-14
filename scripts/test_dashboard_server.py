#!/usr/bin/env python3
"""
Enhanced HTTP server for test dashboard with both static and dynamic views
"""

import http.server
import socketserver
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

class TestDashboardHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler for test dashboard"""
    
    def do_GET(self):
        if self.path == '/api/test-stats':
            self.send_test_stats()
        elif self.path == '/dynamic' or self.path == '/dynamic/':
            self.path = '/test_dashboard/dashboard.html'
            return super().do_GET()
        else:
            # Serve static files
            if self.path == '/':
                # Show a landing page with links to both dashboards
                self.send_landing_page()
                return
            return super().do_GET()
    
    def send_landing_page(self):
        """Send landing page with links to dashboards"""
        html = """<!DOCTYPE html>
<html>
<head>
    <title>AI Persona Orchestrator - Test Dashboards</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            background: #f5f5f5;
            margin: 0;
            padding: 40px;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
        }
        h1 {
            color: #333;
            margin-bottom: 30px;
        }
        .dashboard-links {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        .dashboard-card {
            background: white;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-decoration: none;
            color: #333;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .dashboard-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }
        .dashboard-card h2 {
            margin: 0 0 10px 0;
            color: #667eea;
        }
        .dashboard-card p {
            margin: 0;
            color: #666;
            line-height: 1.5;
        }
        .new-badge {
            display: inline-block;
            background: #4caf50;
            color: white;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 12px;
            margin-left: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>AI Persona Orchestrator - Test Dashboards</h1>
        <div class="dashboard-links">
            <a href="/test_dashboard/index.html" class="dashboard-card">
                <h2>Static Dashboard</h2>
                <p>View latest test results and coverage reports. Auto-refreshes every 30 seconds to show updated statistics.</p>
            </a>
            <a href="/dynamic" class="dashboard-card">
                <h2>Dynamic Dashboard <span class="new-badge">NEW</span></h2>
                <p>Real-time test execution with live logs, start/stop controls, and WebSocket updates. Watch tests run in real-time!</p>
            </a>
        </div>
        <div style="margin-top: 40px; text-align: center; color: #666;">
            <p>Note: For the Dynamic Dashboard, ensure the test runner service is running:</p>
            <code style="background: #e0e0e0; padding: 5px 10px; border-radius: 3px;">python3 scripts/test_runner_service.py</code>
        </div>
    </div>
</body>
</html>"""
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def send_test_stats(self):
        """Send current test statistics as JSON"""
        stats = self.get_test_stats()
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(stats).encode())
    
    def get_test_stats(self):
        """Get current test statistics"""
        stats = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "coverage": 0,
            "last_run": None
        }
        
        # Try to read latest test results
        reports_dir = Path("test_reports")
        if reports_dir.exists():
            latest = reports_dir / "latest"
            if latest.exists() and latest.is_symlink():
                summary_file = latest / "summary.json"
                if summary_file.exists():
                    with open(summary_file) as f:
                        summary = json.load(f)
                        stats["last_run"] = summary.get("timestamp")
                
                # Try to parse junit.xml for detailed stats
                junit_file = latest / "junit.xml"
                if junit_file.exists():
                    # Simple XML parsing (in production, use xml.etree)
                    content = junit_file.read_text()
                    if 'tests="' in content:
                        total = content.split('tests="')[1].split('"')[0]
                        stats["total_tests"] = int(total)
                    if 'failures="' in content:
                        failures = content.split('failures="')[1].split('"')[0]
                        stats["failed"] = int(failures)
                    if 'errors="' in content:
                        errors = content.split('errors="')[1].split('"')[0]
                        stats["failed"] += int(errors)
                    
                    stats["passed"] = stats["total_tests"] - stats["failed"] - stats["skipped"]
                
                # Try to get coverage
                coverage_file = latest / "coverage.json"
                if coverage_file.exists():
                    with open(coverage_file) as f:
                        coverage_data = json.load(f)
                        if "totals" in coverage_data:
                            percent = coverage_data["totals"].get("percent_covered", 0)
                            stats["coverage"] = round(percent, 1)
        
        return stats

def run_server(port=8080):
    """Run the test dashboard server"""
    print(f"🚀 Starting Test Dashboard Server on http://localhost:{port}")
    print(f"📊 Dashboard: http://localhost:{port}/test_dashboard/")
    print(f"📁 Reports: http://localhost:{port}/test_reports/")
    print("\nPress Ctrl+C to stop the server\n")
    
    os.chdir(Path(__file__).parent.parent)  # Go to project root
    
    with socketserver.TCPServer(("", port), TestDashboardHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 Shutting down server...")
            httpd.shutdown()

if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run_server(port)
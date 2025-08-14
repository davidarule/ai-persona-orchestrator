#!/usr/bin/env python3
"""
Simple HTTP server for test dashboard with auto-refresh
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
        else:
            # Serve static files
            if self.path == '/':
                self.path = '/test_dashboard/index.html'
            return super().do_GET()
    
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
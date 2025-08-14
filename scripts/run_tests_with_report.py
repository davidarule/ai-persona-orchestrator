#!/usr/bin/env python3
"""
Run tests and generate HTML reports with coverage
"""

import subprocess
import os
import sys
import datetime
import json
from pathlib import Path

def run_tests():
    """Run tests with coverage and generate reports"""
    
    print("🧪 Running AI Persona Orchestrator Tests...\n")
    
    # Create reports directory
    reports_dir = Path("test_reports")
    reports_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = reports_dir / timestamp
    report_dir.mkdir(exist_ok=True)
    
    # Run tests with coverage and generate HTML report
    cmd = [
        "pytest",
        "tests/",
        "--cov=backend",
        "--cov-report=html:" + str(report_dir / "coverage"),
        "--cov-report=term",
        "--cov-report=json:" + str(report_dir / "coverage.json"),
        "--html=" + str(report_dir / "pytest_report.html"),
        "--self-contained-html",
        "--junit-xml=" + str(report_dir / "junit.xml"),
        "-v"
    ]
    
    print(f"📂 Reports will be saved to: {report_dir}")
    print(f"🔧 Running command: {' '.join(cmd)}\n")
    
    # Run the tests
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Print output
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    # Create summary file
    summary = {
        "timestamp": timestamp,
        "exit_code": result.returncode,
        "report_dir": str(report_dir),
        "coverage_html": str(report_dir / "coverage" / "index.html"),
        "pytest_html": str(report_dir / "pytest_report.html"),
        "junit_xml": str(report_dir / "junit.xml")
    }
    
    # Save summary
    with open(report_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    # Create latest symlink
    latest_link = reports_dir / "latest"
    if latest_link.exists():
        latest_link.unlink()
    latest_link.symlink_to(report_dir.name)
    
    print("\n" + "="*60)
    print("📊 Test Reports Generated:")
    print(f"   Coverage Report: {report_dir / 'coverage' / 'index.html'}")
    print(f"   Test Report: {report_dir / 'pytest_report.html'}")
    print(f"   Latest Report: {reports_dir / 'latest' / 'pytest_report.html'}")
    print("="*60)
    
    # Open in browser if available
    if sys.platform == "darwin":  # macOS
        subprocess.run(["open", str(report_dir / "pytest_report.html")])
    elif sys.platform == "linux":
        subprocess.run(["xdg-open", str(report_dir / "pytest_report.html")])
    
    return result.returncode

if __name__ == "__main__":
    # Install required plugin if not present
    try:
        import pytest_html
    except ImportError:
        print("📦 Installing pytest-html...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pytest-html"])
    
    sys.exit(run_tests())
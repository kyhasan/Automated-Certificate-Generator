"""
Local Web Dashboard Server for Automated Certificate Generator
Runs a zero-dependency HTTP server and opens the browser interface.
"""

import os
import sys
import io
import json
import socket
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from cert_generator import run_automation
from netlify_deployer import load_dotenv

# Ensure .env is loaded
load_dotenv()

# Global state for background job and logs
job_state = {
    "status": "idle",       # "idle", "running", "completed", "failed"
    "logs": "",
    "site_url": None,
    "lock": threading.Lock()
}

class LogCapture(io.StringIO):
    """Custom stdout stream capturing logs in memory and forwarding to original stdout."""
    def __init__(self, original_stdout):
        super().__init__()
        self.original_stdout = original_stdout

    def write(self, s):
        super().write(s)
        self.original_stdout.write(s)
        self.original_stdout.flush()
        with job_state["lock"]:
            job_state["logs"] = self.getvalue()

def execute_generation(payload):
    """Worker thread running cert_generator automation pipeline."""
    original_stdout = sys.stdout
    log_capture = LogCapture(original_stdout)
    sys.stdout = log_capture

    try:
        with job_state["lock"]:
            job_state["status"] = "running"
            job_state["site_url"] = None

        url = payload.get("url")
        category = payload.get("category") or None
        rounds = payload.get("rounds") or None
        site_name = payload.get("site_name") or None
        deploy = bool(payload.get("deploy", True))

        run_automation(
            tournament_url=url,
            category=category,
            total_rounds=rounds,
            template_file="cert.png",
            output_dir="certificates",
            html_file="index.html",
            save_csv=True,
            deploy=deploy,
            site_name=site_name
        )

        # Parse live URL from captured logs if deployed
        full_logs = log_capture.getvalue()
        site_url = None
        for line in full_logs.splitlines():
            if "Published to:" in line or "Site is LIVE at:" in line:
                parts = line.split("http")
                if len(parts) > 1:
                    site_url = "http" + parts[1].strip()

        with job_state["lock"]:
            job_state["status"] = "completed"
            job_state["site_url"] = site_url
            job_state["error_message"] = None

    except Exception as exc:
        err_msg = str(exc)
        print(f"\n[ERROR] Pipeline failed: {err_msg}", file=sys.stderr)
        log_capture.write(f"\n[ERROR] Pipeline failed: {err_msg}\n")
        with job_state["lock"]:
            job_state["status"] = "failed"
            job_state["error_message"] = err_msg
    finally:
        sys.stdout = original_stdout

class DashboardHandler(BaseHTTPRequestHandler):
    """HTTP request handler for web dashboard and REST API."""

    def log_message(self, format, *args):
        # Silence default HTTP server console noise
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html_path = os.path.join(os.path.dirname(__file__), "web", "index.html")
            try:
                with open(html_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(404, "web/index.html not found")
        elif self.path == "/api/status":
            with job_state["lock"]:
                res_data = {
                    "status": job_state["status"],
                    "logs": job_state["logs"],
                    "site_url": job_state["site_url"],
                    "error_message": job_state.get("error_message")
                }
            payload = json.dumps(res_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path == "/api/generate":
            with job_state["lock"]:
                if job_state["status"] == "running":
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "A job is already running!"}).encode("utf-8"))
                    return

            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}

            if not data.get("url"):
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Tournament URL is required."}).encode("utf-8"))
                return

            # Start worker thread
            t = threading.Thread(target=execute_generation, args=(data,), daemon=True)
            t.start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started"}).encode("utf-8"))
        else:
            self.send_error(404, "Not Found")

def find_available_port(start_port=5000):
    """Finds an open TCP port."""
    port = start_port
    while port < 6000:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
            port += 1
    return start_port

def start_server(port=5000, auto_open=True):
    port = find_available_port(port)
    server = HTTPServer(("127.0.0.1", port), DashboardHandler)
    url = f"http://localhost:{port}"

    print(f"\n=======================================================")
    print(f"  Chess Certificate Generator - Web Dashboard")
    print(f"  Running locally at: {url}")
    print(f"  Press Ctrl+C in this terminal to stop the server.")
    print(f"=======================================================\n")

    if auto_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.server_close()

if __name__ == "__main__":
    start_server(5000)


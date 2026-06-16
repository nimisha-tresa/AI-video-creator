#!/usr/bin/env python3
"""
Mock ComfyUI HTTP Server
Provides basic endpoints for testing video generation pipeline
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import time


class ComfyUIHandler(BaseHTTPRequestHandler):
    """Mock ComfyUI API handler"""

    def do_GET(self):
        """Handle GET requests"""
        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"status": "ok"}
            self.wfile.write(json.dumps(response).encode())

        elif self.path == "/queue":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({}).encode())

        elif self.path == "/system":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"models": [], "status": "ready"}
            self.wfile.write(json.dumps(response).encode())

        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "not found"}).encode())

    def do_POST(self):
        """Handle POST requests"""
        if self.path == "/prompt":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            prompt_id = f"mock-{int(time.time())}"
            response = {"prompt_id": prompt_id}
            self.wfile.write(json.dumps(response).encode())

        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "not found"}).encode())

    def log_message(self, format, *args):
        """Suppress logging"""
        pass


if __name__ == "__main__":
    httpd = HTTPServer(("0.0.0.0", 8188), ComfyUIHandler)
    print("ComfyUI Mock Server running on http://0.0.0.0:8188")
    httpd.serve_forever()

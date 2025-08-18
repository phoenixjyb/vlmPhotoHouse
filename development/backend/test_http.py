#!/usr/bin/env python3
"""Minimal HTTP server test."""

import http.server
import socketserver
import threading
import time

class TestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "server": "python-builtin"}')
        else:
            self.send_response(404)
            self.end_headers()

def start_server():
    PORT = 8003
    Handler = TestHandler
    with socketserver.TCPServer(("localhost", PORT), Handler) as httpd:
        print(f"Server running at http://localhost:{PORT}")
        print("Try: curl http://localhost:8003/health")
        httpd.serve_forever()

if __name__ == "__main__":
    start_server()

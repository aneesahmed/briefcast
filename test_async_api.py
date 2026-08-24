import os
import time
import requests
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

WEBHOOK_PORT = 9090
API_URL = "http://localhost:8042/api/process-document-async"

webhook_received = False
webhook_data = None

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        global webhook_received, webhook_data
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        webhook_data = json.loads(post_data)
        
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
        
        webhook_received = True

def run_webhook_server():
    server = HTTPServer(('0.0.0.0', WEBHOOK_PORT), WebhookHandler)
    while not webhook_received:
        server.handle_request()

if __name__ == "__main__":
    print("Starting local webhook server on port 9090...")
    webhook_thread = threading.Thread(target=run_webhook_server, daemon=True)
    webhook_thread.start()

    # Create a dummy test file
    test_filename = "test_document.txt"
    with open(test_filename, "w", encoding="utf-8") as f:
        f.write("This is a simple test document to verify the async pipeline and webhook functionality.")

    webhook_url = f"http://localhost:{WEBHOOK_PORT}/webhook"
    print(f"Sending document to API with webhook_url={webhook_url}...")
    
    with open(test_filename, "rb") as f:
        files = {"file": (test_filename, f, "text/plain")}
        data = {"webhook_url": webhook_url}
        response = requests.post(API_URL, files=files, data=data)

    print("Response from API:", response.status_code)
    print("Response Body:", response.json())
    
    print("\nWaiting for webhook callback (this may take a few seconds)...")
    
    # Wait for webhook to be received
    timeout = 120
    start_time = time.time()
    while not webhook_received and time.time() - start_time < timeout:
        time.sleep(1)

    if webhook_received:
        print("\n[SUCCESS] Webhook successfully received!")
        print(json.dumps(webhook_data, indent=2))
    else:
        print("\n[ERROR] Timed out waiting for webhook.")

    # Cleanup
    if os.path.exists(test_filename):
        os.remove(test_filename)

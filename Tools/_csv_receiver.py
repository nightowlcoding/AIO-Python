import http.server, json, base64, pathlib, threading, sys, os

EXPORTS_DIR = pathlib.Path(r"C:\Users\arnol\OneDrive\Desktop\AIO-Python\Toast Exports")
received = {}

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def do_POST(self):
        length = int(self.headers.get('content-length', 0))
        body = self.rfile.read(length)
        data = json.loads(body)
        date_str = data['date']
        csv_b64 = data['csv']
        csv_bytes = base64.b64decode(csv_b64)
        
        location = "Big House Burgers"
        folder = EXPORTS_DIR / f"{date_str}_{location}"
        folder.mkdir(parents=True, exist_ok=True)
        fname = f"Closed_Shifts_{date_str}_{location.replace(' ', '_')}.csv"
        fpath = folder / fname
        fpath.write_bytes(csv_bytes)
        received[date_str] = len(csv_bytes)
        sys.stdout.write(f"Saved {date_str}: {len(csv_bytes)} bytes -> {fname}\n")
        sys.stdout.flush()
        
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')
    
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({'received': len(received), 'dates': list(received.keys())}).encode())

server = http.server.HTTPServer(('127.0.0.1', 9977), Handler)
sys.stdout.write(f"CSV receiver running on port 9977, waiting for {22} dates...\n")
sys.stdout.flush()
server.serve_forever()

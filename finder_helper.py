"""
Finder Helper - ローカルで起動しておくとブラウザからFinderでファイルを開けるようになります
起動: python3 finder_helper.py
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import subprocess

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/reveal':
            path = parse_qs(parsed.query).get('path', [''])[0]
            if path:
                subprocess.run(['open', '-R', path])
            self._respond()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self._respond()

    def _respond(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *args):
        pass  # ログ非表示

print("Finder Helper 起動中 (port 9999)... Ctrl+C で停止")
HTTPServer(('127.0.0.1', 9999), Handler).serve_forever()

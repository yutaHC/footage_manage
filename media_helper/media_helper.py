"""
MediaHelper - Footage Manager クライアントヘルパー
メニューバー常駐アプリ。ポート19876でローカルHTTPサーバーを起動し、
Webアプリからのリクエストを受けてFinderでファイルを開く。
"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import rumps

VERSION = "1.0.0"
CONFIG_PATH = os.path.expanduser("~/.media_helper_config.json")
DEFAULT_CONFIG = {
    "smb_server": "//192.168.101.20",
    "port": 19876,
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # ログ抑制

    def send_json(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == "/ping":
            self.send_json(200, {"status": "ok", "version": VERSION})

        elif parsed.path == "/open":
            path = unquote(params.get("path", [""])[0])
            if not path:
                self.send_json(400, {"error": "path required"})
                return
            try:
                subprocess.run(["open", "-R", path], check=True)
                self.send_json(200, {"status": "opened", "path": path})
            except subprocess.CalledProcessError as e:
                self.send_json(500, {"error": str(e)})

        else:
            self.send_json(404, {"error": "not found"})


class MediaHelperApp(rumps.App):
    def __init__(self):
        self.config = load_config()
        port = self.config.get("port", 19876)
        nas = self.config.get("smb_server", "")

        self._port_item = rumps.MenuItem(f"ポート: {port}")
        self._nas_item = rumps.MenuItem(f"NAS: {nas}")

        super().__init__(
            "🎬",
            menu=[
                rumps.MenuItem("● ヘルパー稼働中"),
                None,
                self._port_item,
                self._nas_item,
                None,
                rumps.MenuItem("設定を開く", callback=self.open_config),
                rumps.MenuItem("再起動", callback=self.restart),
                None,
            ],
        )

        self._start_server(port)

    def _start_server(self, port):
        server = HTTPServer(("127.0.0.1", port), Handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

    def open_config(self, _):
        if not os.path.exists(CONFIG_PATH):
            save_config(DEFAULT_CONFIG)
        subprocess.run(["open", CONFIG_PATH])

    def restart(self, _):
        executable = sys.executable
        subprocess.Popen([executable] + sys.argv)
        rumps.quit_application()


if __name__ == "__main__":
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
    MediaHelperApp().run()

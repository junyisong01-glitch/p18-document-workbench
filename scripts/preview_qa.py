"""Static-only QA visual preview; deliberately has no backend or database access."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

WEB = Path(__file__).resolve().parents[1] / 'web'
class PreviewHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        route = unquote(urlsplit(path).path)
        if route.startswith('/static/'):
            route = route[len('/static/'):]
        else:
            route = route.lstrip('/') or 'index.html'
        target = (WEB / route).resolve()
        return str(target if target.is_relative_to(WEB) else WEB / '__blocked__')
    def do_GET(self):
        if self.path == '/':
            self.send_response(302)
            self.send_header('Location', '/?qa-preview=01')
            self.end_headers()
            return
        if urlsplit(self.path).path.startswith('/api/'):
            self.send_error(404, 'Static preview: business APIs are unavailable')
            return
        super().do_GET()
    def do_POST(self):
        self.send_error(405, 'Static preview never sends model requests')
    def list_directory(self, path):
        self.send_error(404)
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8771)
    args = parser.parse_args()
    with ThreadingHTTPServer(('127.0.0.1', args.port), PreviewHandler) as server:
        print(f'虚构界面预览：http://127.0.0.1:{args.port}/?qa-preview=01', flush=True)
        server.serve_forever()

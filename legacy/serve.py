#!/home/isee/.venvs/data-tools/bin/python
# -*- coding: utf-8 -*-
"""serve.py —— 可视化平台的本地服务：静态页 + 导入接口。

  python serve.py [--root D:/资料/ICBC/Visualizations] [--port 8765]

接口：
  GET  /              驾驶舱页面（数据比页面新时自动重建）
  GET  /api/state     各条线最新数据日期
  POST /api/import    multipart：line=大类, date=数据日期(可选), files=源表
  POST /api/rebuild   只重算、重建页面

后续上服务器时，把这个文件和 build.py / viz.py 一起部署即可（无第三方依赖）。
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
import sys
import traceback
import webbrowser
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import viz

BASE = Path(__file__).resolve().parent
ROOT = viz.ROOT
PAGE = '阜阳分行个人金融经营驾驶舱.html'


def rebuild(root: Path) -> dict:
    data = root / 'data' / 'dashboard_data.json'
    out = root / 'out' / PAGE
    if not data.exists():
        viz.assemble(root)
    r = subprocess.run([sys.executable, str(BASE / 'build.py'), '--data', str(data),
                        '--out', str(out)], capture_output=True, text=True,
                       env={'PYTHONIOENCODING': 'utf-8', 'PATH': '/usr/bin:/bin'})
    ok = r.returncode == 0 and out.exists()
    return {'ok': ok, 'page': str(out), 'stdout': r.stdout[-400:], 'stderr': r.stderr[-800:]}


def parse_multipart(ctype: str, body: bytes) -> tuple[dict, list[tuple[str, bytes]]]:
    """用 email 解析 multipart，避免 cgi 模块在各版本上的差异。"""
    msg = BytesParser(policy=policy.default).parsebytes(
        b'Content-Type: ' + ctype.encode() + b'\r\nMIME-Version: 1.0\r\n\r\n' + body)
    fields: dict[str, str] = {}
    files: list[tuple[str, bytes]] = []
    for part in msg.iter_parts():
        name = part.get_param('name', header='content-disposition')
        fname = part.get_filename()
        payload = part.get_payload(decode=True) or b''
        if fname:
            files.append((fname, payload))
        elif name:
            fields[name] = payload.decode(part.get_content_charset() or 'utf-8', 'replace')
    return fields, files


class Handler(BaseHTTPRequestHandler):
    server_version = 'ICBC-Viz/1.0'

    def log_message(self, fmt, *args):  # 安静一点
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

    # -------------------------------------------------- 工具
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _page(self):
        out = ROOT / 'out' / PAGE
        if not out.exists():
            rebuild(ROOT)
        data = ROOT / 'data' / 'dashboard_data.json'
        if out.exists() and data.exists() and data.stat().st_mtime > out.stat().st_mtime + 1:
            rebuild(ROOT)
        if not out.exists():
            self.send_error(500, 'page not built')
            return
        body = out.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    # -------------------------------------------------- 路由
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/index.html'):
            return self._page()
        if path == '/api/state':
            lines = [{'id': k, 'label': v['label'], 'hint': v['hint'],
                      'as_of': (viz.load_snapshots(k) or [{}])[-1].get('as_of') if viz.load_snapshots(k) else None}
                     for k, v in viz.LINES.items()]
            meta_p = ROOT / 'data' / 'dashboard_data.json'
            meta = {}
            if meta_p.exists():
                try:
                    meta = json.loads(meta_p.read_text('utf-8')).get('meta', {})
                except Exception:
                    pass
            return self._json({'ok': True, 'root': str(ROOT), 'lines': lines, 'meta': meta})
        if path.startswith('/out/'):
            f = ROOT / path.lstrip('/')
            if f.is_file():
                body = f.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n) if n else b''
        if path == '/api/import':
            return self._import(body)
        if path == '/api/rebuild':
            viz.assemble(ROOT)
            return self._json(rebuild(ROOT))
        self.send_error(404)

    def _import(self, body: bytes):
        try:
            fields, files = parse_multipart(self.headers.get('Content-Type', ''), body)
            line = (fields.get('line') or '').strip()
            data_date = (fields.get('date') or '').strip() or None
            if not files:
                return self._json({'ok': False, 'error': '没有收到文件'}, 400)
            r = viz.do_import(line, files, data_date=data_date)
            if r.get('ok'):
                r['build'] = rebuild(ROOT)
                r['state'] = {'meta': viz.assemble(ROOT)['meta']}
            return self._json(r, 200 if r.get('ok') else 400)
        except Exception as exc:
            return self._json({'ok': False, 'error': f'{type(exc).__name__}: {exc}',
                               'trace': traceback.format_exc()[-800:]}, 500)


def main() -> None:
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=str(viz.ROOT))
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--open', action='store_true', help='启动后自动打开浏览器')
    a = ap.parse_args()
    ROOT = Path(a.root)
    viz.paths(ROOT)
    if not (ROOT / 'data' / 'dashboard_data.json').exists():
        viz.assemble(ROOT)
    rebuild(ROOT)
    url = f'http://127.0.0.1:{a.port}/'
    srv = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    print(json.dumps({'ok': True, 'url': url, 'root': str(ROOT), 'page': str(ROOT / 'out' / PAGE)},
                     ensure_ascii=False, indent=1))
    if a.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

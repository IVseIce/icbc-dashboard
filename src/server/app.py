#!/home/isee/.venvs/data-tools/bin/python
# -*- coding: utf-8 -*-
"""app.py —— v2 服务：SPA 静态资源 + JSON API + 导入。

  python server/app.py [--port 8766] [--root D:/资料/ICBC/Visualizations]

路由：
  GET  /                       SPA（web/index.html）
  GET  /assets/*, /vendor/*    静态资源
  GET  /api/all                一次性给全量视图模型（首屏）
  GET  /api/line/<id>          单条线（按需刷新用）
  GET  /api/state              条线时点 + 最近导入
  POST /api/import             multipart 导入
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import traceback
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path(__file__).resolve().parent      # src/server
SRC = BASE.parent                            # src
PROJ = SRC.parent                            # 项目根
sys.path.insert(0, str(SRC))   # viz / parsers
sys.path.insert(0, str(BASE))  # api（同目录）

import api  # noqa: E402
import report as report_mod  # noqa: E402
import viz  # noqa: E402
from domain import catalog as catalog_mod  # noqa: E402

WEB = SRC / 'web'
ROOT = viz.ROOT


class Handler(BaseHTTPRequestHandler):
    server_version = 'ICBC-Viz/2.0'
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

    # ---------------------------------------------------------------- 输出
    def _send(self, body: bytes, ctype: str, code: int = 200, cache: str = 'no-store'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', cache)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(json.dumps(obj, ensure_ascii=False).encode('utf-8'),
                   'application/json; charset=utf-8', code)

    # ---------------------------------------------------------------- GET
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        on = (qs.get('date') or [None])[0] or None
        try:
            if path in ('/', '/index.html'):
                return self._send((WEB / 'index.html').read_bytes(), 'text/html; charset=utf-8')
            if path.startswith(('/assets/', '/vendor/')):
                f = (WEB / path.lstrip('/')).resolve()
                if WEB in f.parents and f.is_file():
                    ctype = mimetypes.guess_type(f.name)[0] or 'application/octet-stream'
                    if f.suffix == '.js':
                        ctype = 'text/javascript; charset=utf-8'
                    return self._send(f.read_bytes(), ctype,
                                      cache='public, max-age=3600' if '/vendor/' in path else 'no-store')
                return self.send_error(404)
            if path == '/api/catalog':
                cat = catalog_mod.catalog()
                dates = api.available_dates()
                all_dates = sorted({d for v in dates.values() for d in v})
                cat['dates'] = dates
                cat['latest'] = all_dates[-1] if all_dates else None
                cat['earliest'] = all_dates[0] if all_dates else None
                return self._json(cat)
            if path == '/api/report/online':
                return self._json(report_mod.build_online(on))
            if path == '/api/report/online.xlsx':
                blob, name = report_mod.online_xlsx(on)
                from urllib.parse import quote
                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                self.send_header('Content-Disposition',
                                 f"attachment; filename*=UTF-8''{quote(name)}")
                self.send_header('Content-Length', str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)
                return
            if path == '/api/all':
                return self._json(api.build_all(on))
            if path.startswith('/api/line/'):
                return self._json(api.build_line(path.rsplit('/', 1)[-1], on))
            if path == '/api/state':
                lines = []
                for k, meta in viz.LINES.items():
                    snaps = viz.load_snapshots(k)
                    lines.append({'id': k, 'label': meta['label'], 'hint': meta['hint'],
                                  'as_of': snaps[-1].get('as_of') if snaps else None,
                                  'snapshots': len(snaps)})
                led = []
                lp = ROOT / 'ledger.jsonl'
                if lp.exists():
                    for line in lp.read_text('utf-8').splitlines()[-12:]:
                        try:
                            led.append(json.loads(line))
                        except Exception:
                            pass
                return self._json({'ok': True, 'root': str(ROOT), 'lines': lines,
                                   'ledger': list(reversed(led))})
            if path == '/api/health':
                return self._json({'ok': True, 'root': str(ROOT)})
            # SPA 兜底：未知路径回首页（hash 路由不会走到这里，但保留）
            return self._send((WEB / 'index.html').read_bytes(), 'text/html; charset=utf-8')
        except FileNotFoundError:
            return self.send_error(404)
        except Exception:
            return self._json({'ok': False, 'error': traceback.format_exc()[-600:]}, 500)

    # ---------------------------------------------------------------- POST
    def do_POST(self):
        path = urlparse(self.path).path
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n) if n else b''
        if path == '/api/import':
            return self._import(body)
        return self.send_error(404)

    def _import(self, body: bytes):
        try:
            fields, files = parse_multipart(self.headers.get('Content-Type', ''), body)
            line = (fields.get('line') or '').strip()
            dd = (fields.get('date') or '').strip() or None
            if not files:
                return self._json({'ok': False, 'error': '没有收到文件'}, 400)
            r = viz.do_import(line, files, data_date=dd)
            if r.get('ok'):
                r['all'] = api.build_all()
            return self._json(r, 200 if r.get('ok') else 400)
        except Exception:
            return self._json({'ok': False, 'error': traceback.format_exc()[-600:]}, 500)


def parse_multipart(ctype: str, body: bytes):
    msg = BytesParser(policy=policy.default).parsebytes(
        b'Content-Type: ' + ctype.encode() + b'\r\nMIME-Version: 1.0\r\n\r\n' + body)
    fields, files = {}, []
    for part in msg.iter_parts():
        name = part.get_param('name', header='content-disposition')
        fname = part.get_filename()
        payload = part.get_payload(decode=True) or b''
        if fname:
            files.append((fname, payload))
        elif name:
            fields[name] = payload.decode(part.get_content_charset() or 'utf-8', 'replace')
    return fields, files


def main():
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8766)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--root', default=str(viz.ROOT))
    a = ap.parse_args()
    ROOT = Path(a.root)
    viz.paths(ROOT)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(json.dumps({'ok': True, 'url': f'http://{a.host}:{a.port}/', 'root': str(ROOT)},
                     ensure_ascii=False), flush=True)
    srv.serve_forever()


if __name__ == '__main__':
    main()

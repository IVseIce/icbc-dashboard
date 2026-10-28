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
import os
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
import auth  # noqa: E402
from version import app_version, build_info  # noqa: E402
import report as report_mod  # noqa: E402
import store  # noqa: E402
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

    # ---------------------------------------------------------------- 口令
    def _token(self) -> str | None:
        t = (self.headers.get('X-Auth') or '').strip()
        if t:
            return t
        qs = parse_qs(urlparse(self.path).query)
        return (qs.get('token') or [None])[0]

    def _session(self) -> dict | None:
        return auth.session(self._token())

    def _need_auth(self) -> dict | None:
        """校验 token；不合格时直接回 401（前端据此清权限、弹口令框）。"""
        sess = self._session()
        if not sess:
            self._json({'ok': False, 'auth': True, 'error': '需要验证口令'}, 401)
            return None
        return sess

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
            if path == '/api/pbs/sales':
                sess = self._need_auth()
                if not sess:
                    return
                from ingest.pbs import BRANCHES, SALES_KEYS
                raw = store.get('pbs_sales') or {}
                sales = {b: {k: float(((raw.get(b) or {}).get(k)) or 0) for k, _ in SALES_KEYS}
                         for b in BRANCHES}
                return self._json({'ok': True, 'sales': sales,
                                   'columns': [{'key': k, 'name': n} for k, n in SALES_KEYS],
                                   'branches': BRANCHES})
            if path == '/api/catalog':
                cat = catalog_mod.catalog()
                dates = api.available_dates()
                all_dates = sorted({d for v in dates.values() for d in v})
                cat['dates'] = dates
                cat['latest'] = all_dates[-1] if all_dates else None
                cat['earliest'] = all_dates[0] if all_dates else None
                # 条线 → 视图模型 key（页面按模块显示"数据截至"，前端不必硬编码）
                cat['line_keys'] = {line: key for key, line in api.LINE_OF.items()}
                cat['roles'] = auth.ROLES
                cat['version'] = app_version()
                cat['build'] = build_info()
                return self._json(cat)
            if path.startswith('/api/report/'):
                sess = self._need_auth()
                if not sess:
                    return
                rest = path[len('/api/report/'):]
                is_xlsx = rest.endswith('.xlsx')
                kind = rest[:-5] if is_xlsx else rest
                prof = report_mod.CAT_OF.get(kind)
                if prof and not auth.can(sess, prof):
                    return self._json({'ok': False, 'error': '当前身份组没有该大类的通报权限'}, 403)
                if not is_xlsx:
                    return self._json(report_mod.build(kind, on))
                blob, name = report_mod.xlsx(kind, on)
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
                sess = self._need_auth()
                if not sess:
                    return
                allowed = catalog_mod.lines_of(sess.get('scope'))
                stats = {r['line']: r for r in store.line_stats()}
                lines = []
                for k, meta in viz.LINES.items():
                    if k not in allowed:
                        continue
                    s = stats.get(k) or {}
                    lines.append({'id': k, 'label': meta['label'], 'hint': meta['hint'],
                                  'as_of': s.get('as_of'), 'snapshots': int(s.get('count') or 0)})
                led = store.recent_imports(12, allowed)
                for rec in led:
                    rec['label'] = (viz.LINES.get(rec.get('line')) or {}).get('label', rec.get('line'))
                return self._json({'ok': True, 'root': str(ROOT), 'lines': lines,
                                   'ledger': led, 'db': store.stats()})
            if path == '/api/health':
                return self._json({'ok': True, 'root': str(ROOT), 'version': app_version(),
                                   'build': build_info(),
                                   'schema': store.stats()['schema'], 'sqlite': store.sqlite_version()})
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
        if path == '/api/auth/login':
            return self._login(body)
        if path == '/api/auth/password':
            return self._set_password(body)
        if path == '/api/auth/logout':
            auth.logout(self._token())
            return self._json({'ok': True})
        if path == '/api/pbs/sales':
            if not self._need_auth():
                return
            return self._pbs_sales(body)
        if path == '/api/import':
            if not self._need_auth():
                return
            return self._import(body)
        return self.send_error(404)

    def _payload(self, body: bytes) -> dict:
        try:
            obj = json.loads(body.decode('utf-8') or '{}')
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def _login(self, body: bytes):
        info = auth.login(self._payload(body).get('password') or '')
        if not info:
            return self._json({'ok': False, 'error': '口令不正确'}, 401)
        return self._json({'ok': True, **info})

    def _set_password(self, body: bytes):
        sess = self._need_auth()
        if not sess:
            return
        if not sess.get('admin'):
            return self._json({'ok': False, 'error': '只有管理员能改口令'}, 403)
        p = self._payload(body)
        return self._json(auth.set_password(p.get('role') or '', p.get('password') or ''))

    def _pbs_sales(self, body: bytes):
        """保存私银产品销售（人工维护的 7 项 × 8 家支行）。"""
        try:
            data = json.loads(body.decode('utf-8') or '{}')
        except Exception:
            return self._json({'ok': False, 'error': '请求体不是合法 JSON'}, 400)
        sales = data.get('sales')
        if not isinstance(sales, dict):
            return self._json({'ok': False, 'error': 'sales 必须是 {支行: {键: 值}}'}, 400)
        clean = viz.pbs_set_sales(sales)
        # 立刻把新值合进最新一期快照，页面/通报马上能看到
        try:
            viz.refresh_pbs_sales()
        except Exception as exc:
            return self._json({'ok': True, 'sales': clean, 'warning': f'已保存，但刷新快照失败：{exc}'})
        return self._json({'ok': True, 'sales': clean})

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
    ap.add_argument('--port', type=int, default=int(os.environ.get('ICBC_PORT') or 8766))
    ap.add_argument('--host', default=os.environ.get('ICBC_HOST') or '127.0.0.1')
    ap.add_argument('--root', default=os.environ.get('ICBC_ROOT') or str(viz.ROOT))
    a = ap.parse_args()
    ROOT = Path(a.root)
    viz.use_root(ROOT)       # 同时同步 store 的库位置（--root 才真的生效）
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(json.dumps({'ok': True, 'url': f'http://{a.host}:{a.port}/', 'root': str(ROOT),
                      'version': app_version(), 'build': build_info()}, ensure_ascii=False), flush=True)
    srv.serve_forever()


if __name__ == '__main__':
    main()

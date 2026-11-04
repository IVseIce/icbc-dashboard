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
from urllib.parse import parse_qs, quote, urlparse

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

    def _file(self, path: Path, name: str, *, download: bool = True):
        """把磁盘上的文件吐出去（原件下载/预览）。

        大文件分块写，避免整份读进内存；文件名按 RFC 5987 编码，中文名不乱码。
        """
        size = path.stat().st_size
        ctype = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        disp = 'attachment' if download else 'inline'
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(size))
        self.send_header('Content-Disposition',
                         f"{disp}; filename*=UTF-8''{quote(name)}")
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                self.wfile.write(chunk)

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
        start = (qs.get('start') or [None])[0] or None
        end = (qs.get('end') or [None])[0] or None
        snap = (qs.get('snap') or [None])[0] or None      # 定期承接：显式指定用哪一期
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
                cat['line_keys'] = api.line_key_map()
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
                    return self._json(report_mod.build(kind, on, start, end, snap))
                blob, name = report_mod.xlsx(kind, on, start, end, snap)
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
                out = api.build_all(on)
                # 定期承接：页面要能用 ?start=&end= 切窗口
                if start or end or snap:
                    try:
                        out['jiepan'] = api.build_jiepan(on, start, end, snap)
                    except Exception as exc:
                        out['jiepan'] = {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
                return self._json(out)
            if path.startswith('/api/line/'):
                return self._json(api.build_line(path.rsplit('/', 1)[-1], on))
            if path == '/api/admin/data':
                sess = self._need_auth()
                if not sess:
                    return
                if not sess.get('admin'):
                    return self._json({'ok': False, 'error': '只有管理员能管理数据'}, 403)
                return self._json(api.admin_lines())
            if path == '/api/admin/period':
                # 某一期的详情：导入批次 + 留档原件
                sess = self._need_auth()
                if not sess:
                    return
                if not sess.get('admin'):
                    return self._json({'ok': False, 'error': '只有管理员能管理数据'}, 403)
                line = (qs.get('line') or [''])[0].strip()
                as_of = (qs.get('as_of') or [''])[0].strip()
                if not line or not as_of:
                    return self._json({'ok': False, 'error': '要指定 line 和 as_of'}, 400)
                r = api.admin_period(line, as_of)
                return self._json(r, 200 if r.get('ok') else 404)
            if path.startswith('/api/source/'):
                # 原件下载 / 预览。管理员，或对该条线有权限的身份组都能拿（原件就是源表，
                # 页面上能看到这期数据的人，没道理看不到它的来源文件）。
                sess = self._need_auth()
                if not sess:
                    return
                rest = path[len('/api/source/'):].strip('/')
                want_preview = rest.endswith('/preview')
                if want_preview:
                    rest = rest[:-len('/preview')].strip('/')
                # GET /api/source/by-path?path=imports/...（老台账没 id 的情况）
                if rest == 'by-path':
                    src = api.source_by_path((qs.get('path') or [''])[0],
                                             (qs.get('name') or [None])[0])
                else:
                    try:
                        fid = int(rest)
                    except ValueError:
                        return self._json({'ok': False, 'error': '原件 id 不合法'}, 400)
                    src = api.source_download(fid)
                if not src.get('ok'):
                    return self._json(src, 404)
                row = src.get('row') or {}
                line = row.get('line') or src.get('line')
                if line and not sess.get('admin'):
                    from domain import catalog as _cat
                    if line not in _cat.lines_of(sess.get('scope')):
                        return self._json({'ok': False,
                                           'error': '当前身份组没有这条线的权限'}, 403)
                p = Path(src['path'])
                if not want_preview:
                    return self._file(p, src['name'])
                from ingest import readers
                try:
                    r = readers.preview(p, src['name'],
                                        sheet=(qs.get('sheet') or [None])[0])
                except Exception as exc:
                    return self._json({'ok': False, 'error': f'预览失败：{exc}'}, 500)
                r['name'] = src['name']
                r['source_id'] = row.get('id')
                return self._json(r)
            if path == '/api/import/files':
                # 导入页「最近导入」点开：这次导入留档了哪些原件
                sess = self._need_auth()
                if not sess:
                    return
                try:
                    lid = int((qs.get('id') or [''])[0])
                except ValueError:
                    return self._json({'ok': False, 'error': '要指定导入记录 id'}, 400)
                r = api.import_files(lid)
                if r.get('ok') and r.get('line') and not sess.get('admin'):
                    from domain import catalog as _cat
                    if r['line'] not in _cat.lines_of(sess.get('scope')):
                        return self._json({'ok': False, 'error': '当前身份组没有这条线的权限'}, 403)
                return self._json(r, 200 if r.get('ok') else 404)
            if path == '/api/jiepan/periods':
                if not self._need_auth():
                    return
                return self._json({'ok': True, 'periods': api.jiepan_periods()})
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
    def _read_body(self) -> bytes:
        """读请求体，**两种传输方式都要认**。

        Chrome 传大文件（FormData 里带 File）时会用 `Transfer-Encoding: chunked`，
        此时没有 `Content-Length`。原来只按 Content-Length 读，就会读到 0 字节 →
        还没等客户端把文件传完就回包 → 连接被判定为损坏，前端只看到
        `TypeError: Failed to fetch`（Chrome 报 ERR_ALPN_NEGOTIATION_FAILED），
        服务端日志里连一行都没有。跟"导入大文件偶尔失败""换台机器就好"这类现象是同一个根因。
        """
        te = (self.headers.get('Transfer-Encoding') or '').lower()
        if 'chunked' in te:
            out = bytearray()
            while True:
                line = self.rfile.readline(65537)
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    size = int(line.split(b';')[0], 16)
                except ValueError:
                    break
                if size == 0:
                    while True:                       # trailer
                        t = self.rfile.readline(65537)
                        if t in (b'\r\n', b'\n', b''):
                            break
                    break
                chunk = self.rfile.read(size)
                out += chunk
                self.rfile.read(2)                    # 每块结尾的 CRLF
                if len(chunk) < size:
                    break
            return bytes(out)
        n = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(n) if n else b''

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()
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
        if path == '/api/import/period':
            # 导入页预填「通报期间」：只读明细表里的数据日期，不做汇总
            if not self._need_auth():
                return
            return self._probe_period(body)
        if path == '/api/jiepan/find':
            if not self._need_auth():
                return
            return self._jiepan_find(body)
        if path in ('/api/admin/delete', '/api/admin/restore', '/api/admin/purge'):
            sess = self._need_auth()
            if not sess:
                return
            if not sess.get('admin'):
                return self._json({'ok': False, 'error': '只有管理员能管理数据'}, 403)
            return self._admin_edit(path, body)
        return self.send_error(404)

    def _admin_edit(self, path: str, body: bytes):
        """软删除 / 恢复 / 彻底删除某一期。POST JSON：{line, as_of[, confirm]}"""
        try:
            try:
                payload = json.loads(body.decode('utf-8') or '{}')
            except ValueError:
                return self._json({'ok': False, 'error': '请求体不是 JSON'}, 400)
            line = (payload.get('line') or '').strip()
            as_of = (payload.get('as_of') or '').strip()
            if not line or not as_of:
                return self._json({'ok': False, 'error': '要指定 line 和 as_of'}, 400)
            if path.endswith('/delete'):
                r = api.admin_delete(line, as_of)
            elif path.endswith('/purge'):
                r = api.admin_purge(line, as_of, payload.get('confirm'))
            else:
                r = api.admin_restore(line, as_of)
            if r.get('ok'):
                r['all'] = api.build_all()      # 让前端一次刷新到位
            return self._json(r, 200 if r.get('ok') else 400)
        except Exception:
            return self._json({'ok': False, 'error': traceback.format_exc()[-600:]}, 500)

    def _probe_period(self, body: bytes):
        """只回「数据日期 + 默认通报期间」，供导入页在提交前预填/提示。"""
        try:
            fields, files = parse_multipart(self.headers.get('Content-Type', ''), body)
            if not files:
                return self._json({'ok': False, 'error': '没有收到文件'}, 400)
            from ingest import downgrade as dg
            r = dg.probe_period(files, as_of=(fields.get('date') or '').strip() or None)
            return self._json(r)
        except ValueError as exc:
            return self._json({'ok': False, 'error': str(exc)})
        except Exception:
            return self._json({'ok': False, 'error': traceback.format_exc()[-400:]}, 500)

    def _jiepan_find(self, body: bytes):
        """定期承接「手动编辑」：在待导入的明细里按客户编号找行。

        只用来查行、不落库；页面拿到后让用户改四列，提交时随 overrides 一起回传。
        """
        try:
            fields, files = parse_multipart(self.headers.get('Content-Type', ''), body)
            custno = (fields.get('custno') or '').strip()
            if not files:
                return self._json({'ok': False, 'error': '没有收到文件'}, 400)
            from ingest import jiepan, readers

            found = None
            bad = []
            for name, blob in files:
                try:
                    sheets = readers.sheets(blob, name)
                except Exception as exc:            # 图片/损坏文件之类，别抛 500
                    bad.append(f'{name}（{type(exc).__name__}）')
                    continue
                for sheet, rows in sheets:
                    try:
                        jiepan._find_header(rows)
                    except ValueError:
                        continue
                    found = rows
                    break
                if found is not None:
                    break
            if found is None and bad:
                return self._json({'ok': False,
                                   'error': '这些文件读不出表格：' + '、'.join(bad)}, 400)
            if found is None:
                return self._json({'ok': False, 'error': '没有在文件里找到定期承接明细表'}, 400)
            return self._json(jiepan.find_rows(found, custno))
        except Exception:
            return self._json({'ok': False, 'error': traceback.format_exc()[-600:]}, 500)

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
            ov = None
            if (fields.get('overrides') or '').strip():
                try:
                    ov = json.loads(fields['overrides'])
                except ValueError:
                    return self._json({'ok': False, 'error': '手动修改的数据格式不对（overrides 不是 JSON）'}, 400)
            # 通报期间（目前只有降级挽回用）：留空 = 数据日期 ~ +6
            ps = (fields.get('period_start') or '').strip() or None
            pe = (fields.get('period_end') or '').strip() or None
            period = {'start': ps, 'end': pe} if (ps or pe) else None
            r = viz.do_import(line, files, data_date=dd, overrides=ov, period=period)
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

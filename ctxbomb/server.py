"""Honeypot independiente: servidor HTTP pasivo (solo biblioteca estándar)."""
import json
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import core


class Alerter:
    def __init__(self, log_file, webhook):
        import os
        self.log_file, self.webhook, self._lock = log_file, webhook, threading.Lock()
        if log_file:
            os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)

    def emit(self, event):
        line = json.dumps(event, ensure_ascii=False)
        with self._lock:
            if self.log_file:
                with open(self.log_file, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            print(line, flush=True)
        if self.webhook and event["level"] == "high":
            threading.Thread(target=self._post, args=(line,), daemon=True).start()

    def _post(self, line):
        try:
            req = urllib.request.Request(self.webhook, data=line.encode(), headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=3).read()
        except Exception:
            pass


def make_handler(cfg, selector, alerter):
    routes = {r["path"]: r for r in cfg["routes"]}
    canary_paths = sorted(routes)
    trust_proxy = cfg.get("trust_proxy", False)
    delay = cfg.get("response_delay_ms", 0) / 1000.0
    bait = cfg.get("bait_index", True)

    class H(BaseHTTPRequestHandler):
        server_version = "nginx"
        sys_version = ""

        def log_message(self, *a):
            pass

        def _ip(self):
            if trust_proxy and self.headers.get("X-Forwarded-For"):
                return self.headers["X-Forwarded-For"].split(",")[0].strip()
            return self.client_address[0]

        def _event(self, path, level="info"):
            return {"ts": datetime.now(timezone.utc).isoformat(), "src_ip": self._ip(),
                    "ua": self.headers.get("User-Agent", ""), "method": self.command, "path": path,
                    "port": self.server.server_address[1], "level": level}

        def _send(self, code, body=b"", ctype="text/plain; charset=utf-8", head=False):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.end_headers()
            if not head:
                self.wfile.write(body)

        def _handle(self, head=False):
            path = self.path.split("?")[0]
            ev = self._event(path)
            if delay:
                time.sleep(delay)
            route = routes.get(path)
            if route:
                chosen = selector.select(route)
                tpl = route.get("template", "raw")
                body = core.render(tpl, "\n\n".join(p.text for p in chosen)).encode("utf-8")
                ev.update(level="high", route=path, template=tpl,
                          payloads=[{"file": p.name, "sha256": p.sha256, "bytes": len(p.data)} for p in chosen])
                alerter.emit(ev)
                return self._send(200, body, core.content_type(tpl), head)
            alerter.emit(ev)
            if bait and path == "/robots.txt":
                return self._send(200, ("User-agent: *\n" + "".join(f"Disallow: {p}\n" for p in canary_paths)).encode(), head=head)
            if bait and path == "/llms.txt":
                return self._send(200, ("# Internal resources\n\n" + "".join(f"- {p}\n" for p in canary_paths)).encode(), head=head)
            if path == "/":
                links = "".join(f'<li><a href="{p}">{p}</a></li>' for p in canary_paths) if cfg.get("index_links") else ""
                page = f"<html><title>Intranet</title><body>Internal portal<ul>{links}</ul></body></html>"
                return self._send(200, page.encode(), "text/html; charset=utf-8", head)
            return self._send(404, b"not found\n", head=head)

        def do_GET(self):
            self._handle()

        def do_HEAD(self):
            self._handle(head=True)

        def _deny(self):
            alerter.emit(self._event(self.path.split("?")[0]))
            self._send(405)

        do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _deny

    return H


def serve(cfg, payloads):
    alerter = Alerter(cfg.get("log_file"), cfg.get("webhook_url"))
    selector = core.Selector(payloads)
    host = cfg.get("listen", {}).get("host", "127.0.0.1")
    port = cfg.get("listen", {}).get("port", 8080)
    srv = ThreadingHTTPServer((host, port), make_handler(cfg, selector, alerter))
    print(f"ctxbomb escuchando en {host}:{port} ({len(cfg['routes'])} rutas señuelo)", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass

"""Generador de configuración nginx: integra los señuelos en un sitio ya en producción.

Salida (todo estático, sin proceso extra): www/ (recursos ya renderizados), ctxbomb-http.conf (contexto http),
ctxbomb-server.conf (dentro del bloque server), robots-snippet.txt y variants.json (atribución).
"""
import itertools
import json
import os
import re

from . import core

SELECTS_NGINX = ("random", "per_pattern", "fixed")  # 'rotate' necesita estado: no existe en nginx estático
MAX_COMBOS = 64
SAFE_PATH = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*$")


def _variants(route, payloads):
    mode, pats = route.get("select", "random"), route["payloads"]
    if mode == "fixed":
        return [[core.find_fixed(payloads, route["file"])]]
    if mode == "per_pattern":
        groups = [core.match(payloads, [p]) for p in pats]
        combos = list(itertools.product(*groups))
        if len(combos) > MAX_COMBOS:
            raise SystemExit(f"{route['path']}: per_pattern genera {len(combos)} combinaciones (máx {MAX_COMBOS}); "
                             "usa patrones más específicos")
        return [list(c) for c in combos]
    return [[p] for p in core.match(payloads, pats)]


def _pcts(n):
    if n == 1:
        return ["*"]
    each = int(100.0 / n * 100) / 100
    return [f"{each}%"] * (n - 1) + ["*"]


def validate_nginx(cfg, payloads):
    errs = core.validate(cfg, payloads, selects=SELECTS_NGINX)
    for r in cfg.get("routes", []):
        if not SAFE_PATH.match(r.get("path", "")):
            errs.append(f"{r.get('path')!r}: caracteres no permitidos en una ruta de nginx")
    return errs


def generate(cfg, payloads, out_dir):
    ng = cfg.get("nginx", {})
    web_root = ng.get("web_root", "/etc/ctxbomb/www").rstrip("/")
    log_file = ng.get("log_file", "/var/log/nginx/ctxbomb.log")
    noindex = ng.get("noindex", True)
    os.makedirs(os.path.join(out_dir, "www"), exist_ok=True)

    http = [
        "# ctxbomb: contexto http (copiar a /etc/nginx/conf.d/ o incluir dentro de http { })",
        "log_format ctxbomb escape=json '{\"ts\":\"$time_iso8601\",\"src_ip\":\"$remote_addr\",'",
        "    '\"xff\":\"$http_x_forwarded_for\",\"host\":\"$host\",\"method\":\"$request_method\",'",
        "    '\"path\":\"$request_uri\",\"ua\":\"$http_user_agent\",\"status\":$status,'",
        "    '\"bytes\":$body_bytes_sent,\"variant\":\"$ctxbomb_variant\",\"level\":\"high\"}';",
        "",
    ]
    server = ["# ctxbomb: incluir DENTRO del bloque server { } del sitio", ""]
    manifest, robots = {}, ["# --- ctxbomb: añadir a robots.txt ---", "User-agent: *"]

    for i, route in enumerate(cfg["routes"]):
        rid, tpl = f"r{i}", route.get("template", "raw")
        ext = "json" if tpl == "json_secret" else "txt"
        variants = _variants(route, payloads)
        os.makedirs(os.path.join(out_dir, "www", rid), exist_ok=True)
        manifest[route["path"]] = {}
        for j, combo in enumerate(variants):
            vid = f"v{j:02d}"
            body = core.render(tpl, "\n\n".join(p.text for p in combo))
            with open(os.path.join(out_dir, "www", rid, f"{vid}.{ext}"), "w", encoding="utf-8") as fh:
                fh.write(body)
            manifest[route["path"]][f"{rid}:{vid}"] = [{"file": p.name, "sha256": p.sha256} for p in combo]
        http.append(f'split_clients "$request_id" $ctxbomb_{rid} {{')
        http += [f'    {pc} "v{j:02d}";' for j, pc in enumerate(_pcts(len(variants)))]
        http += ["}", ""]
        server += [
            f"location = {route['path']} {{",
            "    limit_except GET HEAD { deny all; }",
            f'    set $ctxbomb_variant "{rid}:$ctxbomb_{rid}";',
            f"    alias {web_root}/{rid}/$ctxbomb_{rid}.{ext};",
            "    types { }",
            f'    default_type "{core.content_type(tpl)}";',
            "    etag off;",
            "    if_modified_since off;",
            '    add_header Cache-Control "no-store" always;',
        ]
        if noindex:
            server.append('    add_header X-Robots-Tag "noindex, nofollow" always;')
        server += [f"    access_log {log_file} ctxbomb;", "}", ""]
        robots.append(f"Disallow: {route['path']}")

    files = {"ctxbomb-http.conf": "\n".join(http), "ctxbomb-server.conf": "\n".join(server),
             "robots-snippet.txt": "\n".join(robots) + "\n",
             "variants.json": json.dumps(manifest, indent=1, ensure_ascii=False)}
    for name, content in files.items():
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            fh.write(content + ("\n" if not content.endswith("\n") else ""))
    return manifest

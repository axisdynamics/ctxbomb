import argparse
import sys

from . import core, nginx as ngx, server


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ctxbomb", description="Honeypot de context bombs (independiente o nginx).")
    ap.add_argument("command", choices=["serve", "check", "list", "nginx"])
    ap.add_argument("-c", "--config", required=True)
    ap.add_argument("-o", "--out", help="directorio de salida (solo 'nginx')")
    a = ap.parse_args(argv)
    cfg = core.load_config(a.config)
    payloads = core.load_payloads(cfg["payloads_dir"])
    if a.command == "list":
        for p in payloads:
            print(f"{p.name}  {len(p.data)} B  sha256:{p.sha256[:16]}")
        return 0
    errs = ngx.validate_nginx(cfg, payloads) if a.command == "nginx" else core.validate(cfg, payloads)
    if errs:
        print("\n".join("ERROR: " + e for e in errs), file=sys.stderr)
        return 1
    if a.command == "check":
        print(f"OK: {len(cfg['routes'])} ruta(s), {len(payloads)} payload(s)")
    elif a.command == "nginx":
        if not a.out:
            print("ERROR: 'nginx' necesita -o <directorio>", file=sys.stderr)
            return 1
        m = ngx.generate(cfg, payloads, a.out)
        print(f"OK: configuración nginx generada en {a.out} ({len(m)} ruta(s))")
    else:
        server.serve(cfg, payloads)
    return 0

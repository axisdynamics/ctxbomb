"""Núcleo compartido: carga de payloads, selección, plantillas y validación.

Los payloads se tratan como bytes opacos: nunca se imprimen ni se guardan en logs (solo nombre, tamaño y SHA-256).
"""
import fnmatch
import hashlib
import json
import os
import random
import threading

TEMPLATES = ("raw", "env", "json_secret", "text_note")
SELECTS = ("random", "rotate", "per_pattern", "fixed")


class Payload:
    __slots__ = ("name", "data", "sha256")

    def __init__(self, name, data):
        self.name, self.data = name, data
        self.sha256 = hashlib.sha256(data).hexdigest()

    @property
    def text(self):
        return self.data.decode("utf-8", "replace")


def load_payloads(directory):
    """Carga todos los *.txt de un único directorio plano."""
    if not os.path.isdir(directory):
        return []
    out = []
    for f in sorted(os.listdir(directory)):
        if f.endswith(".txt"):
            with open(os.path.join(directory, f), "rb") as fh:
                out.append(Payload(f, fh.read()))
    return out


def match(payloads, patterns):
    """Payloads cuyo nombre coincide con algún patrón glob (sin duplicados, en orden)."""
    seen, out = set(), []
    for p in payloads:
        if p.name not in seen and any(fnmatch.fnmatch(p.name, pat) for pat in patterns):
            seen.add(p.name)
            out.append(p)
    return out


def find_fixed(payloads, name):
    for p in payloads:
        if p.name == name or p.name == name + ".txt":
            return p
    return None


class Selector:
    """Elige qué payload(s) sirve una ruta en el servidor independiente."""

    def __init__(self, payloads):
        self.payloads = payloads
        self._rot, self._lock = {}, threading.Lock()

    def select(self, route):
        mode, pats = route.get("select", "random"), route["payloads"]
        if mode == "fixed":
            p = find_fixed(self.payloads, route.get("file", ""))
            return [p] if p else []
        if mode == "per_pattern":
            return [random.choice(m) for m in (match(self.payloads, [pt]) for pt in pats) if m]
        pool = match(self.payloads, pats)
        if not pool:
            return []
        if mode == "rotate":
            with self._lock:
                i = self._rot.get(route["path"], 0)
                self._rot[route["path"]] = i + 1
            return [pool[i % len(pool)]]
        return [random.choice(pool)]


def render(template, text):
    """Incrusta el payload en un recurso señuelo. ensure_ascii=False: el texto llega legible, no como \\uXXXX."""
    if template == "env":
        return ("# internal service credentials - DO NOT COMMIT\n"
                "APP_ENV=production\nDB_HOST=db-int-01.corp.local\n"
                f"INTERNAL_NOTE={json.dumps(text, ensure_ascii=False)}\n")
    if template == "json_secret":
        return json.dumps({"ARN": "arn:aws:secretsmanager:eu-west-1:000000000000:secret:prod/internal-AbCdEf",
                           "Name": "prod/internal", "VersionStage": "AWSCURRENT",
                           "SecretString": text}, ensure_ascii=False, indent=2)
    if template == "text_note":
        return f"INTERNAL - handover notes\n=========================\n\n{text}\n"
    return text


def content_type(template):
    return "application/json; charset=utf-8" if template == "json_secret" else "text/plain; charset=utf-8"


def load_config(path):
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    base = os.path.dirname(os.path.abspath(path))
    cfg.setdefault("payloads_dir", "./payloads")
    for k in ("payloads_dir", "log_file"):
        if cfg.get(k) and not os.path.isabs(cfg[k]):
            cfg[k] = os.path.normpath(os.path.join(base, cfg[k]))
    return cfg


def validate(cfg, payloads, selects=SELECTS):
    errs, paths = [], set()
    if not payloads:
        errs.append(f"no hay payloads (*.txt) en {cfg.get('payloads_dir')}")
    if not cfg.get("routes"):
        errs.append("no hay rutas configuradas")
    for r in cfg.get("routes", []):
        p = r.get("path", "")
        if not p.startswith("/"):
            errs.append(f"la ruta debe empezar por '/': {p!r}")
        if p in paths:
            errs.append(f"ruta duplicada: {p}")
        paths.add(p)
        if r.get("template", "raw") not in TEMPLATES:
            errs.append(f"{p}: template debe ser uno de {TEMPLATES}")
        mode = r.get("select", "random")
        if mode not in selects:
            errs.append(f"{p}: select debe ser uno de {selects}")
        pats = r.get("payloads")
        if not pats or not isinstance(pats, list):
            errs.append(f"{p}: 'payloads' debe ser una lista de patrones (ej. [\"zh-*\"])")
            continue
        for pt in pats:
            if not match(payloads, [pt]):
                errs.append(f"{p}: el patrón {pt!r} no coincide con ningún payload")
        if mode == "fixed" and not find_fixed(payloads, r.get("file", "")):
            errs.append(f"{p}: select=fixed necesita 'file' con un payload existente")
    return errs

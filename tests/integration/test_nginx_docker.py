"""Integración: nginx real en contenedor con un sitio 'de producción' simulado + ctxbomb incluido.

Usa los payloads reales, pero solo compara hashes: nunca imprime ni aserta sobre el contenido.
Requiere docker y la imagen nginx:alpine; si no, se omite.
"""
import hashlib, json, os, shutil, subprocess, sys, tempfile, time, unittest, urllib.error, urllib.request, glob, pathlib, warnings
warnings.simplefilter("ignore", ResourceWarning)
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
IMAGE = os.environ.get("NGINX_IMAGE", "nginx:alpine")

def sh(*a, **k):
    return subprocess.run(a, capture_output=True, text=True, **k)

def docker_ok():
    return shutil.which("docker") and sh("docker", "image", "inspect", IMAGE).returncode == 0

SITE = """server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    include /etc/nginx/ctxbomb/ctxbomb-server.conf;   # <- única línea añadida al sitio
    location = /api/health { return 200 'ok-real-site'; }
    location / { try_files $uri $uri/ =404; }
}
"""

@unittest.skipUnless(docker_ok(), "docker o la imagen nginx no disponibles")
class NginxDocker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ctxbomb import core, nginx as ngx
        cls.t = tempfile.mkdtemp(); os.chmod(cls.t, 0o755)
        cfg = core.load_config(os.path.join(ROOT, "config", "nginx.example.json"))
        pl = core.load_payloads(cfg["payloads_dir"])
        assert not ngx.validate_nginx(cfg, pl)
        cls.out = os.path.join(cls.t, "out"); cls.manifest = ngx.generate(cfg, pl, cls.out)
        cls.cfg = cfg
        os.makedirs(os.path.join(cls.t, "site")); os.makedirs(os.path.join(cls.t, "logs")); os.chmod(os.path.join(cls.t, "logs"), 0o777)
        open(os.path.join(cls.t, "site", "default.conf"), "w").write(SITE)
        open(os.path.join(cls.t, "site", "index.html"), "w").write("REAL SITE HOME")
        for r, _, fs in os.walk(cls.t):
            os.chmod(r, 0o755)
            for f in fs: os.chmod(os.path.join(r, f), 0o644)
        os.chmod(os.path.join(cls.t, "logs"), 0o777)
        cls.name = f"ctxbomb-nginx-test-{os.getpid()}"
        v = lambda s, d, m="ro": ["-v", f"{s}:{d}:{m}"]
        r = sh("docker", "run", "-d", "--name", cls.name, "-p", "127.0.0.1::80",
               *v(f"{cls.out}/ctxbomb-http.conf", "/etc/nginx/conf.d/00-ctxbomb-http.conf"),
               *v(f"{cls.out}/ctxbomb-server.conf", "/etc/nginx/ctxbomb/ctxbomb-server.conf"),
               *v(f"{cls.out}/www", "/etc/ctxbomb/www"),
               *v(f"{cls.t}/site/default.conf", "/etc/nginx/conf.d/default.conf"),
               *v(f"{cls.t}/site/index.html", "/usr/share/nginx/html/index.html"),
               *v(f"{cls.t}/logs", "/var/log/nginx", "rw"), IMAGE)
        assert r.returncode == 0, r.stderr
        port = sh("docker", "port", cls.name, "80/tcp").stdout.strip().split(":")[-1]
        cls.base = f"http://127.0.0.1:{port}"
        for _ in range(40):
            try: urllib.request.urlopen(cls.base + "/api/health", timeout=2); break
            except Exception: time.sleep(0.25)

    @classmethod
    def tearDownClass(cls):
        sh("docker", "rm", "-f", cls.name); shutil.rmtree(cls.t, ignore_errors=True)

    def fetch(self, path, method="GET"):
        req = urllib.request.Request(self.base + path, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def route_hashes(self, path):
        rid = f"r{[r['path'] for r in self.cfg['routes']].index(path)}"
        return {hashlib.sha256(open(f, "rb").read()).hexdigest() for f in glob.glob(f"{self.out}/www/{rid}/*")}

    def test_01_nginx_config_valid(self):
        r = sh("docker", "exec", self.name, "nginx", "-t")
        self.assertEqual(r.returncode, 0, "nginx -t falló: " + r.stderr[-300:])

    def test_02_real_site_unaffected(self):
        s, _, b = self.fetch("/"); self.assertEqual((s, b), (200, b"REAL SITE HOME"))
        s, _, b = self.fetch("/api/health"); self.assertEqual((s, b), (200, b"ok-real-site"))
        self.assertEqual(self.fetch("/no-existe")[0], 404)

    def test_03_canary_routes_serve_expected_bytes(self):
        for route in self.cfg["routes"]:
            s, h, b = self.fetch(route["path"])
            self.assertEqual(s, 200, route["path"])
            want_ct = "application/json; charset=utf-8" if route["template"] == "json_secret" else "text/plain; charset=utf-8"
            self.assertEqual(h.get("Content-Type"), want_ct, route["path"])
            self.assertEqual(h.get("X-Robots-Tag"), "noindex, nofollow"); self.assertEqual(h.get("Cache-Control"), "no-store")
            self.assertIn(hashlib.sha256(b).hexdigest(), self.route_hashes(route["path"]), route["path"] + ": cuerpo inesperado")

    def test_04_variants_are_distributed(self):
        for path in ("/.env", "/internal/aws-secret.json"):
            seen = {hashlib.sha256(self.fetch(path)[2]).hexdigest() for _ in range(60)}
            self.assertGreaterEqual(len(seen), 2, path + ": sin variación entre peticiones")
            self.assertTrue(seen <= self.route_hashes(path))

    def test_05_methods(self):
        s, _, b = self.fetch("/.env", "HEAD"); self.assertEqual((s, len(b)), (200, 0))
        self.assertEqual(self.fetch("/.env", "POST")[0], 403)

    def test_06_log_is_json_without_payload_text(self):
        n_before = len(open(f"{self.t}/logs/ctxbomb.log", encoding="utf-8").read().splitlines()) if os.path.exists(f"{self.t}/logs/ctxbomb.log") else 0
        self.fetch("/backup/handover.txt"); self.fetch("/nada"); self.fetch("/")
        time.sleep(0.5)
        raw = open(f"{self.t}/logs/ctxbomb.log", encoding="utf-8").read()
        rows = [json.loads(l) for l in raw.splitlines()]
        self.assertGreater(len(rows), n_before)
        ids = {k for v in self.manifest.values() for k in v}
        last = rows[-1]
        self.assertEqual(last["path"], "/backup/handover.txt"); self.assertEqual(last["status"], 200)
        self.assertIn(last["variant"], ids); self.assertEqual(last["level"], "high")
        self.assertFalse(any(r["path"] in ("/nada", "/") for r in rows), "tráfico normal no debe ir al log del honeypot")
        for marker in ("天安门", "坦克人", "halting"):
            self.assertNotIn(marker, raw)

if __name__ == "__main__":
    unittest.main()

import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from ctxbomb import core, nginx as ngx
from helpers import make_payload_dir

class Core(unittest.TestCase):
    def setUp(self):
        self.d = make_payload_dir(); self.pl = core.load_payloads(self.d)

    def test_match_globs(self):
        self.assertEqual([p.name for p in core.match(self.pl, ["zh-*"])], ["zh-a.txt", "zh-b.txt"])
        self.assertEqual(len(core.match(self.pl, ["zh-*", "zh-a.txt"])), 2)  # sin duplicados

    def test_selector_modes(self):
        s = core.Selector(self.pl)
        r = {"path": "/x", "payloads": ["zh-*"], "select": "rotate"}
        a, b, c = (s.select(r)[0].name for _ in range(3))
        self.assertNotEqual(a, b); self.assertEqual(a, c)
        self.assertEqual(len(s.select({"path": "/y", "payloads": ["zh-*", "bio-*"], "select": "per_pattern"})), 2)
        self.assertEqual(s.select({"path": "/z", "payloads": ["zh-*"], "select": "fixed", "file": "zh-b"})[0].name, "zh-b.txt")

    def test_render_keeps_unicode_and_escapes(self):
        self.assertIn("无害测试字符串 A", core.render("env", "无害测试字符串 A"))
        self.assertEqual(json.loads(core.render("json_secret", 'a"b\nc'))["SecretString"], 'a"b\nc')

    def test_validate(self):
        cfg = {"payloads_dir": self.d, "routes": [{"path": "x", "payloads": ["nope-*"], "select": "zzz", "template": "q"},
                                                    {"path": "/f", "payloads": ["zh-*"], "select": "fixed"}]}
        self.assertGreaterEqual(len(core.validate(cfg, self.pl)), 5)
        ok = {"payloads_dir": self.d, "routes": [{"path": "/ok", "payloads": ["zh-*"]}]}
        self.assertEqual(core.validate(ok, self.pl), [])
        self.assertTrue(core.validate(ok, []))  # sin payloads

    def test_flat_dir_only_txt(self):
        open(os.path.join(self.d, "README.md"), "w").write("x")
        self.assertEqual(len(core.load_payloads(self.d)), 4)

class Nginx(unittest.TestCase):
    def setUp(self):
        self.d = make_payload_dir(); self.pl = core.load_payloads(self.d); self.out = tempfile.mkdtemp()
        self.cfg = {"payloads_dir": self.d, "nginx": {"web_root": "/srv/cb", "log_file": "/var/log/cb.log"},
                    "routes": [{"path": "/.env", "template": "env", "payloads": ["zh-*"]},
                               {"path": "/s.json", "template": "json_secret", "payloads": ["zh-*", "conv-*", "bio-*"], "select": "per_pattern"},
                               {"path": "/n.txt", "template": "raw", "payloads": ["bio-*"], "select": "fixed", "file": "bio-a.txt"}]}

    def test_generate_files_and_conf(self):
        m = ngx.generate(self.cfg, self.pl, self.out)
        self.assertEqual(len(m["/.env"]), 2); self.assertEqual(len(m["/s.json"]), 2); self.assertEqual(len(m["/n.txt"]), 1)
        srv = open(os.path.join(self.out, "ctxbomb-server.conf"), encoding="utf-8").read()
        self.assertIn("location = /.env {", srv); self.assertIn("alias /srv/cb/r1/$ctxbomb_r1.json;", srv)
        self.assertIn("access_log /var/log/cb.log ctxbomb;", srv)
        http = open(os.path.join(self.out, "ctxbomb-http.conf"), encoding="utf-8").read()
        self.assertIn("split_clients", http); self.assertIn("50.0% \"v00\";", http); self.assertIn('* "v01";', http)
        self.assertIn("Disallow: /.env", open(os.path.join(self.out, "robots-snippet.txt")).read())
        self.assertIn("无害测试字符串 A", open(os.path.join(self.out, "www", "r0", "v00.txt"), encoding="utf-8").read())

    def test_rotate_rejected(self):
        self.cfg["routes"][0]["select"] = "rotate"
        self.assertTrue(ngx.validate_nginx(self.cfg, self.pl))

    def test_unsafe_path_rejected(self):
        self.cfg["routes"][0]["path"] = "/a b{"
        self.assertTrue(any("caracteres" in e for e in ngx.validate_nginx(self.cfg, self.pl)))

    def test_combo_cap(self):
        d = tempfile.mkdtemp()
        for i in range(9):
            for pre in ("a", "b", "c"):
                open(os.path.join(d, f"{pre}-{i}.txt"), "w").write(str(i))
        pl = core.load_payloads(d)
        cfg = {"payloads_dir": d, "routes": [{"path": "/x", "payloads": ["a-*", "b-*", "c-*"], "select": "per_pattern"}]}
        with self.assertRaises(SystemExit): ngx.generate(cfg, pl, tempfile.mkdtemp())

if __name__ == "__main__":
    unittest.main()

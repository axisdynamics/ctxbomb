import json, os, sys, tempfile, threading, unittest, urllib.error, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
from http.server import ThreadingHTTPServer
from ctxbomb import core, server
from helpers import make_payload_dir

class Srv(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = make_payload_dir(); cls.log = os.path.join(tempfile.mkdtemp(), "a.jsonl")
        cls.cfg = {"payloads_dir": d, "bait_index": True, "index_links": True,
                   "routes": [{"path": "/env", "template": "env", "payloads": ["zh-a.txt"], "select": "fixed", "file": "zh-a"},
                              {"path": "/all", "template": "json_secret", "payloads": ["zh-*", "conv-*", "bio-*"], "select": "per_pattern"},
                              {"path": "/rot", "template": "raw", "payloads": ["zh-*"], "select": "rotate"}]}
        pl = core.load_payloads(d)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(cls.cfg, core.Selector(pl), server.Alerter(cls.log, None)))
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def get(self, p):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{p}") as r:
            return r.read().decode("utf-8")

    def test_fixed_unicode(self):
        self.assertIn("无害测试字符串 A", self.get("/env"))

    def test_per_pattern_all_three(self):
        body = json.loads(self.get("/all"))["SecretString"]
        self.assertIn("DUMMY-BIO", body); self.assertIn('x"quote', body)

    def test_rotate(self):
        a, b, c = self.get("/rot"), self.get("/rot"), self.get("/rot")
        self.assertNotEqual(a, b); self.assertEqual(a, c)

    def test_log_hash_not_text(self):
        self.get("/env")
        raw = open(self.log, encoding="utf-8").read()
        hi = [json.loads(l) for l in raw.splitlines() if json.loads(l)["level"] == "high"][-1]
        self.assertEqual(len(hi["payloads"][0]["sha256"]), 64); self.assertNotIn("无害测试字符串", raw)

    def test_bait_404_405(self):
        self.assertIn("Disallow: /env", self.get("/robots.txt"))
        with self.assertRaises(urllib.error.HTTPError) as e: self.get("/nothing")
        self.assertEqual(e.exception.code, 404)
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/env", method="POST", data=b"x")
        with self.assertRaises(urllib.error.HTTPError) as e: urllib.request.urlopen(req)
        self.assertEqual(e.exception.code, 405)

if __name__ == "__main__":
    unittest.main()

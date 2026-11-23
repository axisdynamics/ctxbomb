import os, tempfile

# Payloads ficticios: los tests unitarios nunca usan los payloads reales.
DUMMY = {"zh-a.txt": "无害测试字符串 A", "zh-b.txt": "TEST-B", "conv-a.txt": 'x"quote\nnewline', "bio-a.txt": "DUMMY-BIO"}

def make_payload_dir():
    d = tempfile.mkdtemp()
    for n, c in DUMMY.items():
        with open(os.path.join(d, n), "w", encoding="utf-8") as fh:
            fh.write(c)
    return d

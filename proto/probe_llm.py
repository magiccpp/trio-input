"""Quick check of the LLM helper server."""
import json
import sys
import urllib.request as u

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8791"


def post(path, payload, timeout=60):
    r = u.Request(URL + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    return json.loads(u.urlopen(r, timeout=timeout).read())


print("health:", u.urlopen(URL + "/health", timeout=5).read().decode())
print("score jag_:", post("/score", {"context": "jag ", "candidates": ["kan", "看", "can"]}))
print("score 我:", post("/score", {"context": "我", "candidates": ["kan", "看", "can"]}))
print("convert:", post("/convert", {"context": "", "pinyin": "woxiangchifan", "n": 1}))
print("convert ctx:", post("/convert", {"context": "今天天气很好，", "pinyin": "womenqusanbu", "n": 1}))

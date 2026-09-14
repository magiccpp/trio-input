"""End-to-end check of the learning loop: post a few selections, trigger a retrain,
wait for it, and verify the model file was rebuilt and reloaded."""
import json
import os
import sys
import time
import urllib.request as u

URL = "http://127.0.0.1:8766"
MODEL_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "langid_model.json")


def post(path, payload=None):
    r = u.Request(URL + path, data=json.dumps(payload or {}).encode(), headers={"Content-Type": "application/json"})
    return json.loads(u.urlopen(r, timeout=60).read())


def get(path):
    return json.loads(u.urlopen(URL + path, timeout=10).read())


before = os.path.getmtime(MODEL_JSON)
sels = [
    {"input": "she", "raw": "she", "context": "", "text": "she", "lang": "en", "index": 2, "source": "dict", "primary": "zh"},
    {"input": "hen", "raw": "hen", "context": "she is a ", "text": "hen", "lang": "en", "index": 2, "source": "dict", "primary": "zh"},
    {"input": "kubectl", "raw": "kubectl", "context": "", "text": "kubectl", "lang": "en", "index": 1, "source": "raw", "primary": "zh"},
]
for s in sels:
    st = post("/select", s)
print("after selections:", {k: st[k] for k in ("total", "informative", "suggest_retrain")})
print("immediate personalisation for 'she':", [c["text"] for c in post("/compose", {"input": "she", "context": "", "use_llm": False})["candidates"][:3]])

print("retrain ->", post("/retrain")["retrain_status"])
t0 = time.time()
while True:
    st = get("/learning")
    if st["retrain_status"] != "running":
        break
    time.sleep(5)
print(f"retrain {st['retrain_status']} in {time.time()-t0:.0f}s; since_retrain={st['since_retrain']}")
print("model file rebuilt:", os.path.getmtime(MODEL_JSON) > before)
print(st["retrain_log"][-600:])
sys.exit(0 if st["retrain_status"] == "done" else 1)

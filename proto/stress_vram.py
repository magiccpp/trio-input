"""Hammer /score and /predict with long contexts and many candidates, then report VRAM."""
import json
import random
import sys
import time
import urllib.request as u

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8792"
words = ["hej", "jag", "我们", "看", "can", "själv", "kubectl", "believe", "今天", "讨论", "AI", "的", "内容", "hungrig", "don't"]


def post(path, payload):
    r = u.Request(URL + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    return json.loads(u.urlopen(r, timeout=60).read())


def health():
    return json.loads(u.urlopen(URL + "/health", timeout=5).read())


print("before:", health().get("vram_mb"))
t0 = time.time()
for i in range(60):
    ctx = " ".join(random.choice(words) for _ in range(random.randint(5, 120)))
    cands = random.sample(words, 10)
    post("/score", {"context": ctx[-300:], "candidates": cands})
    if i % 10 == 0:
        post("/predict", {"context": ctx[-400:], "max_new_tokens": 8})
print(f"60 score + 6 predict calls in {time.time()-t0:.1f}s")
print("after:", health().get("vram_mb"), "| mem:", health().get("mem_mb"))

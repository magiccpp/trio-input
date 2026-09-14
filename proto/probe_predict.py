"""Show what the predict-ahead endpoint suggests for a few contexts."""
import json
import sys
import time
import urllib.request as u

URL = "http://127.0.0.1:8766"
ctxs = sys.argv[1:] or ["I would like to ", "今天我们讨论一下AI的内容，", "jag skulle vilja ", "hello, how are ", "我们明天", "tack så "]
for c in ctxs:
    t0 = time.perf_counter()
    r = u.Request(URL + "/predict", data=json.dumps({"context": c}).encode(), headers={"Content-Type": "application/json"})
    j = json.loads(u.urlopen(r, timeout=30).read())
    print(f"{c!r:32} -> {j.get('text')!r:36} units={j.get('units')} {(time.perf_counter()-t0)*1000:.0f} ms")

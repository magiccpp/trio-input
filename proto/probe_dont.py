import json
import urllib.request as u

for ctx in ["jag är hungrig , ", "jag är hungrig, ", "I "]:
    r = u.Request("http://127.0.0.1:8766/compose", data=json.dumps({"input": "donät", "raw": "don't", "context": ctx,
                  "sv_hint": True, "use_llm": True}).encode(), headers={"Content-Type": "application/json"})
    j = json.loads(u.urlopen(r, timeout=60).read())
    print(repr(ctx), [(c["text"], c["source"], c.get("llm"), c.get("score")) for c in j["candidates"][:4]])

"""Show what /compose returns for one context+input, with and without the LLM.
usage: python proto/probe_case.py "I would " like
"""
import json
import sys
import urllib.request as u

URL = "http://127.0.0.1:8766"
ctx, inp = sys.argv[1], sys.argv[2]
if ctx == "-":          # PowerShell drops empty-string arguments; "-" means no context
    ctx = ""
for use_llm in (False, True):
    r = u.Request(URL + "/compose", data=json.dumps({"input": inp, "context": ctx, "use_llm": use_llm}).encode(),
                  headers={"Content-Type": "application/json"})
    j = json.loads(u.urlopen(r, timeout=60).read())
    print(f"use_llm={use_llm} probs={j['probs']} llm_used={j['llm_used']} llm_ms={j['llm_ms']}")
    for c in j["candidates"][:8]:
        print(f"   {c['text']:12} {c['lang']} {c['source']:5} prior={c.get('prior')} llm={c.get('llm')} score={c.get('score')}")

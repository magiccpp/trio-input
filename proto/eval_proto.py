"""Type realistic mixed sentences through the prototype backend and measure
top-1 accuracy with and without the LLM.

usage: python proto/eval_proto.py [http://127.0.0.1:8766]
Each case: (preceding text, typed word, expected top candidate).
Swedish is typed ASCII-folded, as on a keyboard without å/ä/ö keys.
"""
import json
import sys
import time
import urllib.request as u

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8766"

CASES = [
    # Chinese
    ("", "nihao", "你好"),
    ("", "woxiangchifan", "我想吃饭"),
    ("我们明天", "qu", "去"),
    ("今天天气", "henhao", "很好"),
    ("", "zhongguo", "中国"),
    ("我在", "shanghai", "上海"),
    ("我很", "xihuan", "喜欢"),
    ("他", "shi", "是"),
    ("这个", "hen", "很"),
    # English
    ("", "hello", "hello"),
    ("hello ", "world", "world"),
    ("I want to ", "buy", "buy"),
    ("this is ", "a", "a"),
    ("this is a ", "test", "test"),
    ("we ", "can", "can"),
    ("", "kubectl", "kubectl"),
    ("the ", "man", "man"),
    ("I would ", "like", "like"),
    ("I would like to ", "go", "go"),
    ("we ", "like", "like"),
    ("she is a ", "hen", "hen"),
    ("it is ", "so", "so"),
    # spelling
    ("hi, I ", "beleve", "believe"),
    ("we ", "recieved", "received"),
    ("jag ", "sjlav", "själv"),
    ("det är ", "mycet", "mycket"),
    # Swedish (ascii-folded typing)
    ("", "hej", "hej"),
    ("hej ", "jag", "jag"),
    ("jag ", "kan", "kan"),
    ("jag ", "sjalv", "själv"),
    ("det ", "ar", "är"),
    ("det är ", "bra", "bra"),
    ("vi ", "ses", "ses"),
    ("tack sa ", "mycket", "mycket"),
    ("jag ", "far", "får"),
    ("en ", "man", "man"),
    ("vi ", "gar", "går"),
    ("jag skulle vilja ", "ha", "ha"),
    ("det var ", "kul", "kul"),
    # mixed
    ("我喜欢 ", "python", "python"),
    ("I love ", "beijing", "北京"),
    ("jag bor i ", "beijing", "北京"),
    ("we went to ", "shanghai", "上海"),
    ("他说 ", "hej", "hej"),
    ("我们 ", "can", "can"),
    ("jag ", "ai", "爱"),
    ("我 ", "ar", "är"),
]


def compose(inp, ctx, use_llm):
    r = u.Request(URL + "/compose", data=json.dumps({"input": inp, "context": ctx, "use_llm": use_llm}).encode(),
                  headers={"Content-Type": "application/json"})
    return json.loads(u.urlopen(r, timeout=60).read())


def run(use_llm):
    ok, rows, ms = 0, [], []
    for ctx, inp, exp in CASES:
        t0 = time.perf_counter()
        res = compose(inp, ctx, use_llm)
        ms.append((time.perf_counter() - t0) * 1000)
        top = [c["text"] for c in res["candidates"][:5]]
        hit = bool(top) and top[0] == exp
        ok += hit
        rows.append((hit, ctx, inp, exp, top))
    return ok, rows, sum(ms) / len(ms)


if __name__ == "__main__":
    status = json.loads(u.urlopen(URL + "/status", timeout=5).read())
    print("LLM:", status)
    for use_llm in ([False, True] if status.get("llm") else [False]):
        ok, rows, avg = run(use_llm)
        print(f"\n=== use_llm={use_llm}: top-1 {ok}/{len(rows)}  avg {avg:.0f} ms/keystroke")
        for hit, ctx, inp, exp, top in rows:
            if not hit:
                print(f"  MISS ctx={ctx!r:14} typed={inp:12} want={exp:6} got={top}")

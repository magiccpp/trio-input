"""pinyin -> (most frequent Chinese word, count) from data/zh_cn_50k.txt, so the fast
path can weigh Chinese exactly like the English/Swedish exact-word boost.
Output: proto/zh_pinyin_freq.json  {"de": ["的", 5344325], "women": ["我们", 812345], ...}
"""
import json
import re
from pathlib import Path

from pypinyin import Style, lazy_pinyin

HERE = Path(__file__).resolve().parent
src = HERE / "data" / "zh_cn_50k.txt"
out = HERE.parent / "proto" / "zh_pinyin_freq.json"
CJK = re.compile(r"^[一-鿿]+$")

best: dict[str, tuple[str, int]] = {}
for line in src.read_text(encoding="utf-8", errors="ignore").splitlines():
    parts = line.split()
    if len(parts) != 2 or not CJK.match(parts[0]):
        continue
    w, c = parts[0], int(parts[1])
    py = "".join(lazy_pinyin(w, style=Style.NORMAL, errors="ignore")).replace("ü", "v")
    if not re.fullmatch(r"[a-z]+", py):
        continue
    if py not in best or c > best[py][1]:
        best[py] = (w, c)
out.write_text(json.dumps(best, ensure_ascii=False), encoding="utf-8")
print(f"wrote {out}: {len(best)} pinyin keys; de -> {best.get('de')}, women -> {best.get('women')}, shi -> {best.get('shi')}")

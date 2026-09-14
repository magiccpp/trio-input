"""Train a tiny character n-gram language classifier (zh-pinyin / en / sv)
and export it as a Lua table for the RIME filter.

Inputs (data/):
  en_50k.txt     word<space>count   (hermitdave/FrequencyWords)
  sv_50k.txt     word<space>count
  zh_cn_50k.txt  word<space>count   -> converted to toneless pinyin via pypinyin

Output:
  ../rime/lua/langid_model.lua
"""
from __future__ import annotations

import math
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from pypinyin import Style, lazy_pinyin

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
OUT = HERE.parent / "rime" / "lua" / "langid_model.lua"

MIN_N, MAX_N = 1, 4
MAX_FEATURES = 40000
MAX_WORD_FEATURES = 30000
ALPHA = 0.5  # add-k smoothing
random.seed(7)
word_feats: dict[str, list[tuple[str, float]]] = defaultdict(list)

FOLD = str.maketrans({"å": "a", "ä": "a", "ö": "o", "é": "e", "ü": "u"})
CJK = re.compile(r"[一-鿿]")


def read_freq(path: Path) -> list[tuple[str, int]]:
    out = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.strip().split()
        if len(parts) != 2:
            continue
        w, c = parts[0], int(parts[1])
        out.append((w, c))
    return out


def ngrams(s: str):
    s = "^" + s + "$"
    for n in range(MIN_N, MAX_N + 1):
        for i in range(len(s) - n + 1):
            yield s[i : i + n]


def latin_ok(w: str) -> bool:
    return re.fullmatch(r"[a-zåäöéü]+", w) is not None


def build_samples():
    """Return {cls: [(text, weight), ...]}"""
    samples: dict[str, list[tuple[str, float]]] = defaultdict(list)

    # English: ascii words
    en = [(w.lower(), c) for w, c in read_freq(DATA / "en_50k.txt") if latin_ok(w.lower())]
    # Swedish: both real spelling and ascii-folded (what the user actually types)
    sv = [(w.lower(), c) for w, c in read_freq(DATA / "sv_50k.txt") if latin_ok(w.lower())]
    # Chinese words -> pinyin
    zh_words = [(w, c) for w, c in read_freq(DATA / "zh_cn_50k.txt") if CJK.search(w)]
    zh = []
    for w, c in zh_words:
        py = "".join(lazy_pinyin(w, style=Style.NORMAL, errors="ignore"))
        if py and re.fullmatch(r"[a-z]+", py):
            zh.append((py, c))

    def add(cls, items, fold):
        # damp frequencies (log) so the head doesn't dominate the n-grams
        for w, c in items:
            wt = math.log1p(c)
            samples[cls].append((w, wt))
            word_feats[cls].append((w, math.sqrt(c)))
            if fold:
                f = w.translate(FOLD)
                if f != w:
                    samples[cls].append((f, wt * 0.7))
                    word_feats[cls].append((f, math.sqrt(c)))

    add("en", en, fold=False)
    add("sv", sv, fold=True)
    add("zh", zh, fold=False)

    # Synthetic multi-token pinyin strings (users type whole phrases without spaces)
    zh_top = [w for w, _ in zh[:8000]]
    for _ in range(20000):
        k = random.randint(2, 4)
        samples["zh"].append(("".join(random.choice(zh_top) for _ in range(k)), 1.5))
    # Synthetic english / swedish bigrams typed without space (rare, but keep balance)
    en_top = [w for w, _ in en[:6000]]
    sv_top = [w.translate(FOLD) for w, _ in sv[:6000]]
    for _ in range(3000):
        samples["en"].append(("".join(random.sample(en_top, 2)), 1.0))
        samples["sv"].append(("".join(random.sample(sv_top, 2)), 1.0))
    return samples


def train(samples):
    classes = sorted(samples)
    counts = {c: Counter() for c in classes}
    total_feat = Counter()
    total_word = Counter()
    for c in classes:
        for text, wt in samples[c]:
            for g in ngrams(text):
                counts[c][g] += wt
                total_feat[g] += wt
        # whole-word feature, weighted by raw frequency (sqrt) so that very
        # common words ("and", "the", "jag") dominate the n-gram evidence
        for text, wt in word_feats[c]:
            counts[c]["W:" + text] += wt
            total_word["W:" + text] += wt
    feats = [g for g, _ in total_feat.most_common(MAX_FEATURES)]
    feats += [g for g, _ in total_word.most_common(MAX_WORD_FEATURES)]
    V = len(feats)
    logp = {}
    denom = {c: sum(counts[c][g] for g in feats) + ALPHA * V for c in classes}
    unseen = {c: math.log(ALPHA / denom[c]) for c in classes}
    for g in feats:
        logp[g] = [math.log((counts[c][g] + ALPHA) / denom[c]) for c in classes]
    return classes, feats, logp, unseen


def predict(text, classes, logp, unseen):
    s = [0.0] * len(classes)
    for g in list(ngrams(text)) + ["W:" + text]:
        row = logp.get(g)
        for i, c in enumerate(classes):
            s[i] += row[i] if row else unseen[c]
    m = max(s)
    e = [math.exp(x - m) for x in s]
    z = sum(e)
    return {c: e[i] / z for i, c in enumerate(classes)}


def evaluate(samples, classes, logp, unseen):
    ok = n = 0
    for c in classes:
        for text, _ in random.sample(samples[c], min(3000, len(samples[c]))):
            p = predict(text, classes, logp, unseen)
            n += 1
            ok += max(p, key=p.get) == c
    print(f"held-in accuracy: {ok/n:.3f} on {n}")
    for t in ["nihao", "woxiangchifan", "hello", "world", "hej", "sjalv", "själv",
              "tack", "jag", "kan", "and", "kommer", "zhongguo", "computer", "dator",
              "ar", "a", "i", "the", "det", "wo", "ni", "shi", "de", "man", "bra"]:
        p = predict(t, classes, logp, unseen)
        print(f"{t:16s}", "  ".join(f"{c}={p[c]:.2f}" for c in classes))


def export(classes, feats, logp, unseen):
    def lua_str(s):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

    lines = ["-- generated by train_langid.py; char n-gram naive Bayes", "local M = {}"]
    lines.append("M.classes = {" + ", ".join(lua_str(c) for c in classes) + "}")
    lines.append("M.min_n = %d" % MIN_N)
    lines.append("M.max_n = %d" % MAX_N)
    lines.append("M.unseen = {" + ", ".join("%.4f" % unseen[c] for c in classes) + "}")
    lines.append("M.p = {")
    for g in feats:
        lines.append("[%s]={%s}," % (lua_str(g), ",".join("%.3f" % v for v in logp[g])))
    lines.append("}")
    lines.append("return M")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("wrote", OUT, OUT.stat().st_size // 1024, "KB")
    # JSON copy for the standalone Python prototype
    import json
    jout = HERE.parent / "proto" / "langid_model.json"
    jout.parent.mkdir(exist_ok=True)
    jout.write_text(json.dumps({"classes": classes, "min_n": MIN_N, "max_n": MAX_N,
                                "unseen": [unseen[c] for c in classes],
                                "p": {g: [round(v, 3) for v in logp[g]] for g in feats}},
                               ensure_ascii=False), encoding="utf-8")
    print("wrote", jout, jout.stat().st_size // 1024, "KB")


def add_selections(samples, path: Path, weight: float = 12.0):
    """Mix in the user's own selections (proto/data/selections.jsonl): each record's
    typed input is a labelled sample for the language of the chosen candidate.
    Corrections (non-first candidate, or a language the fast path got wrong) count double."""
    import json
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        inp, lang = (r.get("input") or "").lower(), r.get("lang")
        if not inp or lang not in ("zh", "en", "sv") or not latin_ok(inp.translate(FOLD)):
            continue
        wt = weight * (2.0 if r.get("informative") else 0.25)   # default acceptances are weak evidence
        samples[lang].append((inp, wt))
        # word feature ≈ a word seen ~40k times in the corpus per correction: enough to
        # flip an ambiguous word, not enough to override strong context
        word_feats[lang].append((inp, 8.0 * wt))
        if lang == "sv":
            f = inp.translate(FOLD)
            if f != inp:
                samples[lang].append((f, wt))
                word_feats[lang].append((f, 8.0 * wt))
        n += 1
    print(f"added {n} user selections from {path}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--selections", type=Path, help="proto/data/selections.jsonl to personalise the model")
    args = ap.parse_args()
    samples = build_samples()
    if args.selections and args.selections.exists():
        add_selections(samples, args.selections)
    for c in samples:
        print(c, len(samples[c]), "samples")
    classes, feats, logp, unseen = train(samples)
    evaluate(samples, classes, logp, unseen)
    export(classes, feats, logp, unseen)

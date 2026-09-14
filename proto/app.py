"""Standalone trilingual input prototype (no Windows IME registration).

  python proto/app.py            -> http://127.0.0.1:8765
  LLM_URL=http://127.0.0.1:8791  -> optional local LLM helper (proto/llm_server.py)

Pipeline per keystroke (POST /compose):
  fast path : luna_pinyin (rime.dll) + EN/SV prefix dictionaries + char n-gram langid
  smart path: local LLM scores the top candidates given the preceding text and
              (for pinyin) proposes its own conversion.
"""
from __future__ import annotations

import bisect
import json
import math
import os
import re
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rime_engine import RimeEngine  # noqa: E402
import shell_mode  # noqa: E402

try:
    from pypinyin import Style, lazy_pinyin
except ImportError:  # pragma: no cover
    lazy_pinyin = None

LLM_CONVERT = os.environ.get("LLM_CONVERT", "0") == "1"   # generation is unreliable on tiny models
LLM_PRIOR_W = float(os.environ.get("LLM_PRIOR_W", "2.0"))


def pinyin_of(text: str) -> str:
    if not lazy_pinyin:
        return ""
    return "".join(lazy_pinyin(text, style=Style.NORMAL, errors="ignore")).replace("ü", "v")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PORT = int(os.environ.get("PORT", "8766"))
LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:8791")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "2.0"))

CJK = re.compile(r"[一-鿿]")
FOLD = str.maketrans({"å": "a", "ä": "a", "ö": "o", "é": "e", "ü": "u"})

# ------------------------------------------------------------------ n-gram model
MODEL_JSON = HERE / "langid_model.json"
_model: dict = {}


def load_model():
    m = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
    _model.update(classes=m["classes"], unseen=m["unseen"], p=m["p"], min_n=m["min_n"], max_n=m["max_n"],
                  mtime=MODEL_JSON.stat().st_mtime)


load_model()


def classify(text: str) -> dict[str, float]:
    CLASSES, UNSEEN, P = _model["classes"], _model["unseen"], _model["p"]
    text = text.lower()
    s = "^" + text + "$"
    acc = [0.0] * len(CLASSES)
    feats = ["W:" + text]
    for n in range(_model["min_n"], _model["max_n"] + 1):
        feats += [s[i : i + n] for i in range(len(s) - n + 1)]
    for g in feats:
        row = P.get(g)
        for k in range(len(CLASSES)):
            acc[k] += row[k] if row else UNSEEN[k]
    # short strings: the n-gram model is over-confident (she/the/can are all valid
    # pinyin), so soften it and let the word-frequency / context signals decide
    temp = 1.0 + 4.0 / max(1, len(text))
    acc = [a / temp for a in acc]
    m = max(acc)
    e = [math.exp(a - m) for a in acc]
    z = sum(e)
    return {c: e[i] / z for i, c in enumerate(CLASSES)}


# ------------------------------------------------------------------ learning from the user
DATA = HERE / "data"
DATA.mkdir(exist_ok=True)
SELECTIONS = DATA / "selections.jsonl"
USER_WORDS = DATA / "user_words.json"
RETRAIN_INFORMATIVE = int(os.environ.get("RETRAIN_INFORMATIVE", "50"))   # corrections
RETRAIN_TOTAL = int(os.environ.get("RETRAIN_TOTAL", "300"))              # any selections
_learn_lock = threading.Lock()
_user_words: dict[str, dict] = {}          # folded code -> {text -> {"lang", "n"}}
_stats = {"total": 0, "informative": 0, "since_retrain": 0, "informative_since_retrain": 0,
          "last_retrain": None, "retrain_status": "idle", "retrain_log": ""}


def _load_learning():
    if USER_WORDS.exists():
        try:
            d = json.loads(USER_WORDS.read_text(encoding="utf-8"))
            _user_words.update(d.get("words", {}))
            _stats.update({k: v for k, v in d.get("stats", {}).items() if k in _stats})
        except Exception as e:
            print("user_words load failed:", e, file=sys.stderr)


def _save_learning():
    USER_WORDS.write_text(json.dumps({"words": _user_words, "stats": {k: _stats[k] for k in
                                      ("total", "informative", "since_retrain", "informative_since_retrain", "last_retrain")}},
                                     ensure_ascii=False, indent=0), encoding="utf-8")


_load_learning()


def record_selection(rec: dict) -> dict:
    """rec: input, raw, context, text, lang, index, shown(list), primary(fast-path lang)"""
    text = rec.get("text", "")
    if not text or not rec.get("input"):
        return _stats
    code = rec["input"].lower().translate(FOLD)
    informative = rec.get("index", 0) != 0 or rec.get("primary") != rec.get("lang")
    ctx_lang = history_lang(rec.get("context", "")) or "-"      # "-" = sentence start
    rec = {**rec, "informative": informative, "ctx_lang": ctx_lang, "ts": int(time.time())}
    with _learn_lock:
        with SELECTIONS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        # A correction is real evidence. Accepting the default is weak evidence (the
        # user may just have had no better option), so it counts a quarter.
        w = 1.0 if informative else 0.25
        entry = _user_words.setdefault(code, {}).setdefault(text, {"lang": rec.get("lang", "en"), "n": 0, "ctx": {}})
        entry["n"] += w
        entry.setdefault("ctx", {})[ctx_lang] = entry["ctx"].get(ctx_lang, 0) + w
        _stats["total"] += 1
        _stats["since_retrain"] += 1
        if informative:
            _stats["informative"] += 1
            _stats["informative_since_retrain"] += 1
        _save_learning()
    return learning_status()


def learning_status() -> dict:
    s = dict(_stats)
    s["suggest_retrain"] = (_stats["retrain_status"] != "running" and
                            (_stats["informative_since_retrain"] >= RETRAIN_INFORMATIVE or _stats["since_retrain"] >= RETRAIN_TOTAL))
    s["thresholds"] = {"informative": RETRAIN_INFORMATIVE, "total": RETRAIN_TOTAL}
    return s


def retrain_async() -> dict:
    """Re-fit the n-gram model with the user's selections mixed in (background thread)."""
    if _stats["retrain_status"] == "running":
        return learning_status()
    _stats["retrain_status"] = "running"
    _stats["retrain_log"] = ""

    def run():
        import subprocess
        py = sys.executable
        cmd = [py, str(ROOT / "train" / "train_langid.py"), "--selections", str(SELECTIONS)]
        try:
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}   # Windows console is GBK
            out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800, env=env)
            _stats["retrain_log"] = (out.stdout or "")[-3000:] + (out.stderr or "")[-1500:]
            if out.returncode == 0:
                load_model()
                with _learn_lock:
                    _stats.update(since_retrain=0, informative_since_retrain=0, last_retrain=int(time.time()), retrain_status="done")
                    _save_learning()
            else:
                _stats["retrain_status"] = "failed"
        except Exception as e:
            _stats["retrain_status"] = "failed"
            _stats["retrain_log"] += repr(e)

    threading.Thread(target=run, daemon=True).start()
    return learning_status()


# ------------------------------------------------------------------ dictionaries
def load_dict(name: str) -> tuple[list[str], dict[str, list[tuple[str, int]]]]:
    """returns (sorted codes, code -> [(text, weight)])"""
    by_code: dict[str, list[tuple[str, int]]] = {}
    body = False
    for line in (ROOT / "rime" / f"{name}.dict.yaml").read_text(encoding="utf-8").splitlines():
        if line.strip() == "...":
            body = True
            continue
        if not body or not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        text, code, w = parts[0], parts[1], int(parts[2])
        by_code.setdefault(code, []).append((text, w))
    for v in by_code.values():
        v.sort(key=lambda x: -x[1])
    return sorted(by_code), by_code


EN_CODES, EN = load_dict("en_words")
SV_CODES, SV = load_dict("sv_words")
# pinyin -> (most frequent Chinese word, count); built by train/build_zh_freq.py
try:
    ZH_FREQ: dict[str, list] = json.loads((HERE / "zh_pinyin_freq.json").read_text(encoding="utf-8"))
except FileNotFoundError:
    ZH_FREQ = {}
EN_SET = {t for v in EN.values() for t, _ in v}
SV_SET = {t for v in SV.values() for t, _ in v}


def prefix_lookup(codes: list[str], table: dict, prefix: str, limit: int) -> list[tuple[str, int]]:
    """exact match first, then completions by weight -> [(text, weight)]"""
    out: list[tuple[str, int, int]] = []  # (text, exact, weight)
    i = bisect.bisect_left(codes, prefix)
    j = i
    while j < len(codes) and codes[j].startswith(prefix) and j - i < 400:
        for text, w in table[codes[j]]:
            out.append((text, 1 if codes[j] == prefix else 0, w))
        j += 1
    out.sort(key=lambda x: (-x[1], -x[2]))
    seen, res = set(), []
    for t, _, w in out:
        if t not in seen:
            seen.add(t)
            res.append((t, w))
        if len(res) >= limit:
            break
    return res


# ------------------------------------------------------------------ spelling correction
ALPHA = "abcdefghijklmnopqrstuvwxyz"


def _edits1(w: str):
    splits = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    yield from (a + b[1:] for a, b in splits if b)                                   # delete
    yield from (a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1)            # transpose
    yield from (a + c + b[1:] for a, b in splits if b for c in ALPHA)               # replace
    yield from (a + c + b for a, b in splits for c in ALPHA)                        # insert


def spell_candidates(typed: str, table: dict, limit: int = 4) -> list[tuple[str, int, int]]:
    """dictionary words within edit distance 1 (or 2 for longer words) of the typed
    code -> [(text, weight, distance)], best first. Codes are ASCII-folded, so this
    also finds själv for 'sjlav'."""
    if len(typed) < 4 or typed in table:
        return []
    found: dict[str, tuple[int, int]] = {}
    e1 = set(_edits1(typed))
    for c in e1:
        for t, w in table.get(c, []):
            if t not in found or w > found[t][0]:
                found[t] = (w, 1)
    if not found and len(typed) >= 5:
        for c1 in e1:
            for c2 in _edits1(c1):
                if c2 in table:
                    for t, w in table[c2]:
                        if t not in found or w > found[t][0]:
                            found[t] = (w, 2)
    out = sorted(found.items(), key=lambda kv: (kv[1][1], -kv[1][0]))
    return [(t, w, d) for t, (w, d) in out[:limit]]


def cand_lang(text: str) -> str:
    if CJK.search(text):
        return "zh"
    if re.search(r"[åäöÅÄÖ]", text):
        return "sv"
    lt = text.lower()
    a, b = lt in EN_SET, lt in SV_SET
    if a and not b:
        return "en"
    if b and not a:
        return "sv"
    p = classify(text)
    return "sv" if p["sv"] > p["en"] else "en"


def history_langs(context: str, n: int = 3) -> list[str]:
    """languages of the last n words/phrases, most recent first"""
    words = re.findall(r"[一-鿿]+|[A-Za-zÅÄÖåäöÉé']+", context)
    return [cand_lang(w) for w in reversed(words[-n:])]


def history_lang(context: str) -> str | None:
    h = history_langs(context, 1)
    return h[0] if h else None


# ------------------------------------------------------------------ LLM helper
def llm_post(path: str, payload: dict, timeout: float = LLM_TIMEOUT):
    req = urllib.request.Request(LLM_URL + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


_llm_info = {"ok": False, "model": None, "checked": 0.0}


def llm_available() -> bool:
    now = time.time()
    if now - _llm_info["checked"] < 10:
        return _llm_info["ok"]
    _llm_info["checked"] = now
    try:
        with urllib.request.urlopen(LLM_URL + "/health", timeout=0.5) as r:
            _llm_info.update(ok=True, model=json.loads(r.read()).get("model"))
    except Exception:
        _llm_info.update(ok=False)
    return _llm_info["ok"]


# ------------------------------------------------------------------ composer
rime = RimeEngine()
rime_lock = threading.Lock()


NORDIC_RE = re.compile(r"[åäö]")


def diacritics_ok(cand: str, inp: str) -> bool:
    """the candidate must carry the å/ä/ö the user explicitly typed (and no others
    where the user typed a plain letter)"""
    c = cand.lower()
    for i, ch in enumerate(inp):
        if i >= len(c):
            break
        if ch in "åäö" and c[i] != ch:
            return False
        if ch in "ao" and c[i] in "åäö":
            return False
    return True


_latest_seq: dict[str, int] = {}     # per page session: newest compose request seen


def _is_stale(table: dict, sid: str, req_seq: int | None) -> bool:
    """keystrokes arrive faster than the LLM answers: only the newest request per
    page session is worth a GPU/CPU round-trip"""
    if req_seq is None:
        return False
    table[sid] = max(table.get(sid, 0), req_seq)
    return req_seq < table[sid]


def compose_shell(raw: str, line: str) -> dict:
    """command-line mode: literal token first, then completions from history / knowledge base"""
    t0 = time.perf_counter()
    cands = [{"text": raw, "lang": "sh", "source": "raw", "prior": 0.0}]
    comps = shell_mode.command_completions(raw) if not line.strip() else shell_mode.token_completions(line, raw)
    cands += [{"text": t, "lang": "sh", "source": "cmd", "prior": 0.0} for t in comps if t != raw]
    return {"preedit": raw, "candidates": cands[:12], "probs": {"sh": 1.0}, "primary": "sh", "shell": True,
            "fast_ms": round((time.perf_counter() - t0) * 1000, 1), "llm_ms": 0, "llm_used": False}


def compose(inp: str, context: str, sv_hint: bool, use_llm: bool, raw: str = "", req_seq: int | None = None,
            sid: str = "-", shell: str = "auto") -> dict:
    line = context.rsplit("\n", 1)[-1]
    typed_cmd = (raw or inp).lower()
    at_line_start = not line.strip()
    if shell == "on" or (shell == "auto" and (shell_mode.is_shell_line(line) or
                                              (at_line_start and shell_mode.is_shell_line(typed_cmd)))):
        return compose_shell(raw or inp, line)
    t0 = time.perf_counter()
    stale = _is_stale(_latest_seq, sid, req_seq)
    inp = inp.lower()
    typed = inp.translate(FOLD)          # dictionary codes are ASCII-folded
    has_nordic = bool(NORDIC_RE.search(inp))
    sv_hint = sv_hint or has_nordic
    if not typed:
        return {"candidates": [], "probs": {}, "preedit": ""}

    p = classify(inp)                     # the model knows ä/ö/å n-grams
    # context 1: the language of the preceding words (most recent counts most)
    for i, h in enumerate(history_langs(context, 3)):
        p[h] *= (3.0, 1.5, 1.2)[i]
    # context 2: the script mix of the last ~40 characters. "今天我们讨论一下AI" is a
    # Chinese sentence with one English token in it, not an English context.
    tail = context[-40:]
    n_cjk = len(CJK.findall(tail))
    n_lat = len(re.findall(r"[A-Za-zÅÄÖåäö]", tail))
    if n_cjk + n_lat:
        r = n_cjk / (n_cjk + n_lat)
        p["zh"] *= 1 + 4 * r
        p["en"] *= 1 + 2 * (1 - r)
        p["sv"] *= 1 + 2 * (1 - r)
    if sv_hint:
        p["sv"] *= 4

    with rime_lock:
        preedit, zh = rime.candidates(typed, limit=8) if not has_nordic else ("", [])
    en = prefix_lookup(EN_CODES, EN, typed, 8) if not has_nordic else []
    sv = prefix_lookup(SV_CODES, SV, typed, 12)
    if has_nordic:
        sv = [(t, w) for t, w in sv if diacritics_ok(t, inp)][:8]
    # spelling: "beleve" -> believe. Only when the typed word is a dead end (no exact
    # match and no completion in that dictionary) — while a word is still being typed
    # the completions are the right suggestions.
    spelled: set[str] = set()
    if not en and not has_nordic:
        en = [(t, w) for t, w, d in spell_candidates(typed, EN)]
        spelled.update(t for t, _ in en)
    if not sv:
        sv = [(t, w) for t, w, d in spell_candidates(typed, SV)]
        spelled.update(t for t, _ in sv)
    if spelled:
        # a plausible correction counts as evidence for that language too
        for lang in ("en", "sv"):
            if any(t in spelled for t, _ in (en if lang == "en" else sv)):
                w = max((w for t, w in (en if lang == "en" else sv) if t in spelled), default=0)
                p[lang] *= 1 + math.log1p(w) ** 2 / 24

    # an exact hit on a common word is strong evidence for that language
    # (many English words are also valid pinyin: like, can, hen, man ...)
    def exact_weight(table, key):
        return max((w for t, w in table.get(key, [])), default=0)
    for lang, table in (("en", EN), ("sv", SV)):
        w = exact_weight(table, typed)
        if w > 0:
            p[lang] *= 1 + math.log1p(w) ** 2 / 6      # 1M occurrences -> x33, 1k -> x9
    # ... and the same for Chinese: 的 (de), 是 (shi), 我们 (women) are as common as "the"
    if typed in ZH_FREQ and not has_nordic:
        p["zh"] *= 1 + math.log1p(ZH_FREQ[typed][1]) ** 2 / 6
    # what the user picked before for this exact input (immediate personalisation;
    # the retrain folds it into the n-gram model for generalisation). Choices made
    # in the same surrounding language count fully, others only a little; the
    # effect is capped so a few habitual commits can't bury a whole language.
    ctx_lang = history_lang(context) or "-"
    learned = {}
    for t, e in _user_words.get(typed, {}).items():
        same = e.get("ctx", {}).get(ctx_lang, 0)
        eff = min(3.0, same + 0.25 * (e["n"] - same))
        if eff > 0:
            learned[t] = {"lang": e["lang"], "n": eff}
    for t, e in learned.items():
        p[e["lang"]] *= 1 + 3.0 * e["n"]
    z = sum(p.values())
    p = {k: v / z for k, v in p.items()}

    cands: list[dict] = []
    seen = set()

    # at the start of a line a typed prefix of a command name is offered too ("kube" -> kubectl)
    cmd_comps = shell_mode.command_completions(typed, 3) if (not line.strip() and len(typed) >= 2 and typed.isalpha()) else []

    # frequency prior (log, relative to the most frequent candidate of that language)
    en_max = math.log1p(en[0][1]) if en else 0.0
    sv_max = math.log1p(sv[0][1]) if sv else 0.0

    def add(text, lang, source, prior=0.0):
        if text and text not in seen:
            seen.add(text)
            if text in spelled and source == "dict":
                source, prior = "spell", prior - 1.0       # one edit away: a small penalty
            cands.append({"text": text, "lang": lang, "source": source, "prior": round(prior, 2)})

    exact_latin = any(t.lower().translate(FOLD) == typed for t, _ in en + sv)
    order = sorted(["zh", "en", "sv"], key=lambda k: -p[k])
    buckets = {
        # rime's own order is a strong prior for choices within Chinese; the
        # small LLM mainly decides *between* languages
        "zh": [(t, "rime", -1.2 * i) for i, t in enumerate(zh)],
        "en": [(t, "dict", 0.7 * (math.log1p(w) - en_max)) for t, w in en],
        "sv": [(t, "dict", 0.7 * (math.log1p(w) - sv_max)) for t, w in sv],
    }
    order = [o for o in order if buckets[o]] + [o for o in order if not buckets[o]]
    primary = order[0]
    raw_first = primary != "zh" and not exact_latin and typed.isalpha()
    has_fix = any(t in spelled for t, _, _ in buckets[primary])
    if raw_first and not has_fix:
        add(inp if has_nordic else typed, primary, "raw", -3.0)
    for i, (t, s, pr) in enumerate(buckets[primary]):
        add(t, primary, s, pr)
        if raw_first and has_fix and i == 0:          # the correction first, the literal word second
            add(inp if has_nordic else typed, primary, "raw", -3.0)
    # the literal keys (e.g. don't, we're) stay reachable as candidate 2
    raw = (raw or "").lower()
    if raw and raw != inp and "'" in raw and re.fullmatch(r"[a-z']+", raw):
        seen.add(raw)
        cands.insert(min(1, len(cands)), {"text": raw, "lang": "en", "source": "raw", "prior": -1.0})
    # escape hatches: the best candidate of every other language is ALWAYS visible
    # (positions 3 and 5), whatever the probabilities say
    for k, pos in ((order[1], 2), (order[2], 4)):
        if buckets[k]:
            t, s, pr = buckets[k][0]
            if t not in seen:
                seen.add(t)
                cands.insert(min(pos, len(cands)), {"text": t, "lang": k, "source": s, "prior": round(pr, 2)})
    for k in order[1:]:
        for t, s, pr in buckets[k]:
            add(t, k, s, pr)

    for t in reversed(cmd_comps):        # right after the typed text: "kube" -> kubectl
        if t not in seen:
            seen.add(t)
            cands.insert(min(1, len(cands)), {"text": t, "lang": "sh", "source": "cmd", "prior": -2.0})

    # previously chosen words for this input go first (most chosen first)
    for t, e in sorted(learned.items(), key=lambda kv: -kv[1]["n"]):
        idx = next((i for i, c in enumerate(cands) if c["text"] == t), None)
        if idx is None:
            cands.insert(0, {"text": t, "lang": e["lang"], "source": "learned", "prior": 0.0})
        else:
            c = cands.pop(idx)
            c["source"] = "learned"
            c["prior"] = c.get("prior", 0.0) + 2.0 * math.log1p(e["n"])
            cands.insert(0, c)
    if learned:
        seen.update(learned)

    # an exact dictionary match beats another language's completions
    def is_exact(c):
        if c["source"] == "learned":
            return True
        if c["source"] == "raw":       # the literal typed word is not a dictionary match
            return False
        return c["lang"] != "zh" and c["text"].lower().translate(FOLD) == typed
    if cands and not is_exact(cands[0]) and cands[0]["lang"] != "zh":
        for i, c in enumerate(cands[:6]):
            if is_exact(c) and p[c["lang"]] >= 0.15:
                cands.insert(0, cands.pop(i))
                break

    # command-name completions stay right behind the typed text whatever else was promoted
    cmd_idx = [i for i, c in enumerate(cands) if c["source"] == "cmd"]
    if cmd_idx and cmd_idx[0] > 1:
        moved = [cands[i] for i in cmd_idx]
        cands = [c for c in cands if c["source"] != "cmd"]
        cands[1:1] = moved

    fast_ms = (time.perf_counter() - t0) * 1000
    llm_ms, llm_used, llm_conv = 0.0, False, []
    if use_llm and stale:
        use_llm = False
    if use_llm and llm_available():
        try:
            t1 = time.perf_counter()
            typed_v = typed.replace("v", "v")
            # Only candidates that render the WHOLE typed input are comparable:
            # exact Latin matches, the raw word, and Chinese whose pinyin == input.
            def full(c):
                if c["lang"] == "zh":
                    return pinyin_of(c["text"]) == typed_v
                if c["source"] in ("raw", "learned", "spell"):
                    return True
                return c["text"].lower().translate(FOLD) == typed
            if typed.isalpha() and not exact_latin and not any(c["source"] == "raw" for c in cands):
                cands.append({"text": typed, "lang": order[0] if order[0] != "zh" else "en", "source": "raw", "prior": -3.0})
            if LLM_CONVERT and p["zh"] >= 0.5 and len(typed) >= 4:
                conv = llm_post("/convert", {"context": context, "pinyin": typed, "n": 1})
                llm_conv = [c for c in conv.get("candidates", []) if CJK.search(c) and pinyin_of(c) == typed_v]
                for c in llm_conv:
                    if c not in seen:
                        seen.add(c)
                        cands.append({"text": c, "lang": "zh", "source": "llm", "prior": 0.0})
            scored = [c for c in cands if full(c)][:10]
            rest = [c for c in cands if c not in scored]
            if len(scored) >= 2:
                res = llm_post("/score", {"context": context[-300:], "candidates": [c["text"] for c in scored]})
                for c, s in zip(scored, res["scores"]):
                    c["llm"] = round(s, 2)
                    # LLM evidence + language prior + word-frequency / rime-rank prior.
                    # The literal-apostrophe reading (don't) is not a language guess,
                    # so it gets no language prior: the LLM decides ä vs '.
                    # floor at 2%: the fast-path probabilities are not calibrated enough to
                    # veto the LLM outright (的 at -3 must beat "de" at -15)
                    lang_prior = 0.0 if (c["source"] == "raw" and "'" in c["text"]) else LLM_PRIOR_W * math.log(max(p[c["lang"]], 0.02))
                    c["score"] = round(s + lang_prior + c.get("prior", 0.0), 2)
                scored.sort(key=lambda c: -c["score"])
                cands = scored + rest
            elif scored:
                cands = scored + rest
            llm_ms = (time.perf_counter() - t1) * 1000
            llm_used = True
        except Exception as e:  # LLM is optional: fall back silently
            llm_ms = -1
            print("llm error:", e, file=sys.stderr)

    return {"preedit": preedit or inp, "candidates": cands[:12], "probs": {k: round(v, 3) for k, v in p.items()},
            "primary": cands[0]["lang"] if cands else primary, "fast_ms": round(fast_ms, 1),
            "llm_ms": round(llm_ms, 1), "llm_used": llm_used, "llm_model": _llm_info["model"], "llm_conv": llm_conv}


# ------------------------------------------------------------------ predict ahead
_latest_pred: dict[str, int] = {}
UNIT_RE = re.compile(r"\s*[A-Za-zÅÄÖåäöÉé'’-]+|\s*[一-鿿]+|\s*[0-9][0-9.,:%/-]*|\s*\S")


def predict_ahead(context: str, req_seq: int | None = None, sid: str = "-", shell: str = "auto") -> dict:
    """Next few words from the LLM, split into Tab-sized units (a Latin word incl. its
    leading space, or a run of Chinese characters). In command-line mode the user's own
    history is consulted first; the LLM sees the lines as a shell session."""
    stale = _is_stale(_latest_pred, sid, req_seq)
    line = context.rsplit("\n", 1)[-1]
    is_shell = shell == "on" or (shell == "auto" and shell_mode.is_shell_line(line))
    if is_shell:
        rest = shell_mode.line_suggestion(line)
        if rest:
            return {"text": rest, "units": UNIT_RE.findall(rest), "source": "history", "shell": True}
    if not context.strip() or not llm_available():
        return {"text": "", "units": []}
    if stale:
        return {"text": "", "units": [], "stale": True}
    t0 = time.perf_counter()
    try:
        if is_shell:
            # present the recent lines as a terminal session so the model continues a command
            lines = [l for l in context.split("\n") if l.strip()][-6:]
            prompt = "\n".join("$ " + l for l in lines)
            text = llm_post("/predict", {"context": prompt, "max_new_tokens": 12}, timeout=4.0).get("text", "")
            text = text.split("\n")[0].replace("$ ", "").rstrip()
            # the user ended a token (trailing space): a continuation that glues onto the
            # last token ("ps" + "d") is the model extending the word, not a new argument
            if line.endswith(" ") and text and not text.startswith(" "):
                text = ""
        else:
            text = llm_post("/predict", {"context": context, "max_new_tokens": 8}, timeout=4.0).get("text", "")
    except Exception as e:
        print("predict error:", e, file=sys.stderr)
        return {"text": "", "units": []}
    units = UNIT_RE.findall(text)
    return {"text": text, "units": units, "ms": round((time.perf_counter() - t0) * 1000, 1), "shell": is_shell,
            "source": "llm"}


# ------------------------------------------------------------------ http
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, (HERE / "static" / "index.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/status":
            info = {}
            if llm_available():
                try:
                    with urllib.request.urlopen(LLM_URL + "/health", timeout=0.5) as r:
                        info = json.loads(r.read())
                except Exception:
                    pass
            return self._send(200, json.dumps({"llm": llm_available(), "model": _llm_info["model"], "llm_url": LLM_URL,
                                               "device": info.get("device"), "device_desc": info.get("device_desc"),
                                               "mem_mb": info.get("mem_mb"), "learning": learning_status(),
                                               "shell_cmds": sorted(shell_mode.COMMANDS | set(shell_mode._first_tokens)),
                                               "shell_history": len(shell_mode._history)}).encode())
        if self.path == "/learning":
            return self._send(200, json.dumps(learning_status(), ensure_ascii=False).encode())
        self._send(404, b"{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/compose":
            res = compose(req.get("input", ""), req.get("context", ""), bool(req.get("sv_hint")), bool(req.get("use_llm", True)),
                          req.get("raw", ""), req.get("seq"), str(req.get("sid", "-")), req.get("shell", "auto"))
            return self._send(200, json.dumps(res, ensure_ascii=False).encode())
        if self.path == "/shell_line":
            line = req.get("line", "")
            if req.get("force") or shell_mode.is_shell_line(line):
                shell_mode.add_history(line)
            return self._send(200, json.dumps({"lines": len(shell_mode._history)}).encode())
        if self.path == "/shell_import":
            p = Path(req.get("path", "")).expanduser()
            n = shell_mode.import_history(p) if p.is_file() else 0
            return self._send(200, json.dumps({"imported": n, "lines": len(shell_mode._history)}).encode())
        if self.path == "/select":
            return self._send(200, json.dumps(record_selection(req), ensure_ascii=False).encode())
        if self.path == "/predict":
            return self._send(200, json.dumps(predict_ahead(req.get("context", ""), req.get("seq"), str(req.get("sid", "-")),
                                                            req.get("shell", "auto")), ensure_ascii=False).encode())
        if self.path == "/retrain":
            return self._send(200, json.dumps(retrain_async(), ensure_ascii=False).encode())
        self._send(404, b"{}")


if __name__ == "__main__":
    print(f"trilingual prototype: http://127.0.0.1:{PORT}   LLM: {LLM_URL} ({'up' if llm_available() else 'down'})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()

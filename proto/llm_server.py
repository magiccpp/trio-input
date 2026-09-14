"""Local LLM helper server (runs in WSL on the RTX 3090, plain stdlib HTTP).

POST /score    {"context": "...", "candidates": ["...", ...]}
               -> {"scores": [sum log p(candidate | context) ...], "ms": float}
POST /convert  {"context": "...", "pinyin": "woxiangchifan", "n": 3}
               -> {"candidates": ["我想吃饭", ...], "ms": float}
GET  /health   -> {"model": ..., "device": ...}

MODEL env var selects the HF model id (default Qwen/Qwen3-0.6B, offline cache).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

_local_model = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "llm", "models", "Qwen3-0.6B")
MODEL = os.environ.get("MODEL") or (os.path.abspath(_local_model) if os.path.isdir(_local_model) else "Qwen/Qwen3-0.6B")
PORT = int(os.environ.get("PORT", "8791"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

def disable_triton_overrides():
    """newer torch routes bmm through a Triton kernel that needs a C compiler;
    fall back to the plain CUDA kernel so this runs on a bare WSL install."""
    try:
        from torch._native import registry as _r
        _r._register_all_overrides()
        _r.deregister_op_overrides(disable_dsl_names=["triton", "helion", "cutedsl"], disable_op_symbols=["bmm"])
        _r._print_override_graphs()
        print("torch native Triton overrides disabled", flush=True)
    except Exception as _e:  # noqa
        print("torch native override switch not available:", _e, flush=True)


DEVICE = os.environ.get("DEVICE", "auto")          # auto | cpu | cuda
QUANT = os.environ.get("QUANT", "int8")            # int8 (CPU dynamic quantization) | none
THREADS = int(os.environ.get("THREADS", str(max(1, (os.cpu_count() or 4) // 2))))

def pick_device() -> tuple[str, str]:
    """NVIDIA GPU -> Intel GPU/iGPU (torch XPU) -> CPU. Returns (device, description)."""
    if DEVICE != "auto":
        return DEVICE, "forced by DEVICE env"
    try:
        if torch.cuda.is_available():
            return "cuda", "NVIDIA " + torch.cuda.get_device_name(0)
    except Exception:
        pass
    try:
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return "xpu", torch.xpu.get_device_name(0)
    except Exception:
        pass
    return "cpu", f"CPU ({os.cpu_count()} threads available)"


device, device_desc = pick_device()
dtype = torch.bfloat16 if device in ("cuda", "xpu") else torch.float32
print(f"device order: nvidia -> intel xpu -> cpu; selected {device}: {device_desc}", flush=True)
print(f"loading {MODEL} on {device} (quant={QUANT if device == 'cpu' else 'none'}, threads={THREADS}) ...", flush=True)
if device == "cpu":
    torch.set_num_threads(THREADS)
tok = AutoTokenizer.from_pretrained(MODEL)
INT8_FILE = MODEL.rstrip("\\/") + "-int8.pt"
if device == "cpu" and QUANT == "int8":
    import gc
    import warnings
    if os.path.exists(INT8_FILE):
        # Pre-quantized file (llm/quantize_model.py): the process never holds fp32
        # weights, which is what keeps Windows under ~2 GB (its allocator does not
        # return freed fp32 temporaries).
        print("loading pre-quantized", INT8_FILE, flush=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = torch.load(INT8_FILE, weights_only=False, map_location="cpu").eval()
    else:
        # Quantize each Linear to dynamic int8 one at a time from the bf16 weights.
        print("no pre-quantized file; quantizing in-process (run llm/quantize_model.py to avoid the memory peak)", flush=True)
        from torch.ao.nn.quantized.dynamic import Linear as QLinear
        model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, low_cpu_mem_usage=True).eval()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for name, mod in list(model.named_modules()):
                for child_name, child in list(mod.named_children()):
                    if isinstance(child, torch.nn.Linear):
                        child = child.float()
                        child.qconfig = torch.ao.quantization.default_dynamic_qconfig
                        setattr(mod, child_name, QLinear.from_float(child))
                        del child
        for p in model.parameters():          # remaining bf16 params (norms, embedding)
            if p.dtype == torch.bfloat16 and p.numel() < 10_000_000:
                p.data = p.data.float()
    emb = model.get_input_embeddings()     # keep the big embedding in bf16, upcast its output
    if emb.weight.dtype == torch.bfloat16:
        emb.register_forward_hook(lambda m, i, o: o.float())
    gc.collect()
    try:  # hand the freed fp32 weights back to the OS
        import ctypes
        if sys.platform == "win32":
            ctypes.windll.kernel32.SetProcessWorkingSetSize(ctypes.windll.kernel32.GetCurrentProcess(), -1, -1)
        else:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass
else:
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=dtype, low_cpu_mem_usage=True).to(device).eval()
if tok.pad_token_id is None:
    tok.pad_token = tok.eos_token
if device == "cuda":
    disable_triton_overrides()
print("ready", flush=True)


def mem_mb() -> dict:
    """Process memory. Linux: RSS split into anonymous (heap) and file-backed (cache)
    pages; Windows: working set + private bytes via psapi."""
    out = {}
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class PMC(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                            ("PrivateUsage", ctypes.c_size_t)]
            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            fn = ctypes.windll.kernel32.K32GetProcessMemoryInfo
            fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            fn.restype = wintypes.BOOL
            if fn(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                out = {"WorkingSet": round(pmc.WorkingSetSize / 2**20), "Private": round(pmc.PrivateUsage / 2**20)}
        except Exception:
            pass
        return out
    try:
        with open("/proc/self/status") as f:
            for line in f:
                for k in ("VmRSS", "RssAnon", "RssFile"):
                    if line.startswith(k + ":"):
                        out[k] = round(int(line.split()[1]) / 1024)
    except Exception:
        pass
    return out

SYSTEM = ("You are an input-method engine. The user types Chinese (as pinyin without tones), "
          "English and Swedish, often mixed in one text.")


@torch.inference_mode()
def score(context: str, candidates: list[str]) -> list[float]:
    """sum log p(candidate tokens | context) for each candidate, batched."""
    # log p(cand | context) = log p(context + cand) - log p(context), each tokenized
    # canonically. This is invariant to BPE merges across the boundary
    # ("他"+"是" -> single token "他是"; "the "+"man" -> "the"," man").
    # a trailing space belongs to the next word (" like" is one token), so move it
    # from the context onto the candidates
    stripped = context.rstrip()
    if stripped != context:
        ws = context[len(stripped):]
        context = stripped
        candidates = [ws + c for c in candidates]
    lead = tok("\n", add_special_tokens=False)["input_ids"]  # neutral start token
    ctx_ids = lead + (tok(context, add_special_tokens=False)["input_ids"] if context else [])
    seqs, starts, cand_lens = [ctx_ids], [1], [len(ctx_ids) - 1]   # row 0 = context alone
    for c in candidates:
        full = lead + tok(context + c, add_special_tokens=False)["input_ids"]
        seqs.append(full)
        starts.append(1)
        cand_lens.append(len(full) - 1)
    maxlen = max(len(s) for s in seqs)
    pad = tok.pad_token_id
    input_ids = torch.full((len(seqs), maxlen), pad, dtype=torch.long)
    attn = torch.zeros((len(seqs), maxlen), dtype=torch.long)
    for i, s in enumerate(seqs):
        input_ids[i, : len(s)] = torch.tensor(s)
        attn[i, : len(s)] = 1
    input_ids, attn = input_ids.to(device), attn.to(device)
    logits = model(input_ids=input_ids, attention_mask=attn).logits.float()
    logp = torch.log_softmax(logits[:, :-1], dim=-1)
    tgt = input_ids[:, 1:]
    tok_lp = logp.gather(-1, tgt.unsqueeze(-1)).squeeze(-1)
    totals = []
    for i, s in enumerate(seqs):
        start = starts[i] - 1
        end = len(s) - 1
        totals.append(float(tok_lp[i, start:end].sum()) if cand_lens[i] > 0 else 0.0)
    ctx_lp = totals[0]
    return [t - ctx_lp for t in totals[1:]]


@torch.inference_mode()
def convert(context: str, pinyin: str, n: int = 3) -> list[str]:
    user = (f"Preceding text: {context[-200:]!r}\n"
            f"Pinyin typed now: {pinyin}\n"
            "Write the Chinese characters for this pinyin, considering the preceding text. "
            "Answer with the Chinese characters only.")
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    try:
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    except TypeError:
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    ids = tok(prompt, return_tensors="pt").to(device)
    gen = model.generate(**ids, max_new_tokens=24, do_sample=n > 1, temperature=0.7, top_p=0.9,
                         num_return_sequences=n, pad_token_id=tok.pad_token_id)
    outs = []
    for g in gen:
        text = tok.decode(g[ids["input_ids"].shape[1]:], skip_special_tokens=True)
        text = text.replace("<think>", "").replace("</think>", "").strip().split("\n")[0].strip()
        if text and text not in outs:
            outs.append(text)
    return outs


@torch.inference_mode()
def predict(context: str, max_new_tokens: int = 10, keep_lines: bool = False) -> str:
    """Greedy continuation of the text so far (mixed zh/en/sv), one line at most
    (keep_lines=True returns the raw multi-line continuation for the caller to parse)."""
    context = context[-400:].rstrip()      # a trailing space belongs to the next token
    if not context:
        return ""
    ids = tok(context, return_tensors="pt", add_special_tokens=False).to(device)
    gen = model.generate(**ids, max_new_tokens=max_new_tokens, do_sample=False,
                         repetition_penalty=1.15, pad_token_id=tok.pad_token_id)
    text = tok.decode(gen[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
    if keep_lines:
        return text
    # after a mixed-language line the model sometimes starts a new paragraph first;
    # take the first non-empty line it produces
    text = text.lstrip("\n").split("\n")[0]
    # cut at the last complete word so we never suggest half a token
    m = re.match(r"^(.*?)(?:[A-Za-zÅÄÖåäö]+)?$", text)
    if m and not text.endswith((" ", "。", "，", ".", ",", "!", "?")) and re.search(r"[A-Za-zÅÄÖåäö]$", text):
        text = text[: m.end(1)] if m.end(1) > 0 else ""
    return text.rstrip()


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

    def do_GET(self):
        self._send(200, {"model": MODEL, "device": device, "device_desc": device_desc,
                         "quant": QUANT if device == "cpu" else "none", "threads": THREADS, "mem_mb": mem_mb()})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        t0 = time.perf_counter()
        try:
            if self.path == "/score":
                res = {"scores": score(req.get("context", ""), req["candidates"])}
            elif self.path == "/convert":
                res = {"candidates": convert(req.get("context", ""), req["pinyin"], int(req.get("n", 3)))}
            elif self.path == "/predict":
                res = {"text": predict(req.get("context", ""), int(req.get("max_new_tokens", 10)), bool(req.get("keep_lines")))}
            else:
                return self._send(404, {"error": "no such route"})
        except Exception as e:  # noqa
            return self._send(500, {"error": repr(e)})
        res["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        self._send(200, res)


if __name__ == "__main__":
    # warm up
    score("hej", ["jag", "我", "I"])
    print(f"serving on http://0.0.0.0:{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()

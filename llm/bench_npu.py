"""nuc2: NPU attempts with static shapes.
 A) NPUW LLM pipeline (generate path) — what OpenVINO GenAI uses for LLMs on NPU.
 B) stateless IR reshaped to [1, 32], plain forward, one candidate at a time (scoring).
"""
import os
import subprocess
import sys
import time
import traceback

import openvino as ov
import torch
from optimum.intel import OVModelForCausalLM
from transformers import AutoTokenizer

src = os.path.expanduser("~/trilingual-llm/Qwen3-0.6B")
ir = os.path.expanduser("~/trilingual-llm/Qwen3-0.6B-ov-int8")
ir_nc = os.path.expanduser("~/trilingual-llm/Qwen3-0.6B-ov-int8-nocache")
tok = AutoTokenizer.from_pretrained(src)
if tok.pad_token_id is None:
    tok.pad_token = tok.eos_token
ctx = "jag är hungrig, but I don't care. 今天我们讨论一下AI的内容，"
cands = ["hello", "hej", "jag", "我们", "kan", "看", "can", "själv", "sjalv", "kubectl"]

print("== A) NPU, NPUW LLM pipeline, generate", flush=True)
try:
    cfg = {"NPU_USE_NPUW": "YES", "NPUW_LLM": "YES", "NPUW_LLM_MAX_PROMPT_LEN": "128", "NPUW_LLM_MIN_RESPONSE_LEN": "32"}
    t0 = time.time()
    m = OVModelForCausalLM.from_pretrained(ir, device="NPU", ov_config=cfg, compile=True)
    print(f"   load+compile {time.time()-t0:.1f} s", flush=True)
    g = tok(ctx, return_tensors="pt")
    for i in range(3):
        t = time.time()
        out = m.generate(**g, max_new_tokens=8, do_sample=False)
        print(f"   generate 8 tokens: {(time.time()-t)*1000:6.1f} ms" + ("  (warm-up)" if i == 0 else ""), tok.decode(out[0][g['input_ids'].shape[1]:]), flush=True)
    # scoring one candidate at a time through the same pipeline (prefill only)
    for i in range(2):
        t = time.time()
        for c in cands:
            ids = tok(ctx + c, return_tensors="pt")
            m.generate(**ids, max_new_tokens=1, do_sample=False, output_scores=True, return_dict_in_generate=True)
        print(f"   10 candidates, one prefill each: {(time.time()-t)*1000:6.1f} ms" + ("  (warm-up)" if i == 0 else ""), flush=True)
except Exception as e:
    print("   FAILED:", type(e).__name__, str(e)[:400])

print("\n== B) NPU, stateless IR reshaped to [1,32], plain forward per candidate", flush=True)
try:
    if not os.path.exists(os.path.join(ir_nc, "openvino_model.xml")):
        r = subprocess.run(["optimum-cli", "export", "openvino", "-m", src, "--task", "text-generation",
                            "--weight-format", "int8", ir_nc], capture_output=True, text=True)
        print(r.stderr[-600:], flush=True)
    for device in ("NPU", "GPU", "CPU"):
        try:
            t0 = time.time()
            m = OVModelForCausalLM.from_pretrained(ir_nc, device=device, compile=False, use_cache=False)
            m.reshape(1, 32)
            m.compile()
            print(f"   [{device}] load+compile {time.time()-t0:.1f} s", flush=True)
            batch = [tok(ctx + c, return_tensors="pt", padding="max_length", max_length=32, truncation=True) for c in cands]
            with torch.inference_mode():
                for i in range(3):
                    t = time.time()
                    for b in batch:
                        m(input_ids=b["input_ids"], attention_mask=b["attention_mask"])
                    print(f"   [{device}] 10 candidates x 32 tok, batch 1 each: {(time.time()-t)*1000:6.1f} ms" + ("  (warm-up)" if i == 0 else ""), flush=True)
        except Exception as e:
            print(f"   [{device}] FAILED:", type(e).__name__, str(e)[:300])
except Exception:
    traceback.print_exc(limit=2)

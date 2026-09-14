"""nuc2: compare OpenVINO devices (CPU / GPU=iGPU / NPU) on the input method's workload:
a batched forward pass scoring ~10 short candidates (the /score call) and a short greedy
generation (the /predict call). Exports Qwen3-0.6B to OpenVINO IR (int8 weights) once.

usage: .venv-ov/bin/python bench_ov.py [model_dir]
"""
import os
import subprocess
import sys
import time
import traceback

src = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/trilingual-llm/Qwen3-0.6B")
ir = os.path.expanduser("~/trilingual-llm/Qwen3-0.6B-ov-int8")
if not os.path.exists(os.path.join(ir, "openvino_model.xml")):
    print("exporting to OpenVINO IR (int8 weights) ...", flush=True)
    subprocess.run([sys.executable, "-m", "optimum.exporters.openvino", "--help"], capture_output=True)
    r = subprocess.run(["optimum-cli", "export", "openvino", "-m", src, "--task", "text-generation-with-past",
                        "--weight-format", "int8", ir], capture_output=True, text=True)
    print(r.stdout[-800:], r.stderr[-1500:], flush=True)

import openvino as ov  # noqa: E402
import torch  # noqa: E402
from optimum.intel import OVModelForCausalLM  # noqa: E402
from transformers import AutoTokenizer  # noqa: E402

core = ov.Core()
print("OpenVINO", ov.__version__, "devices:", core.available_devices, flush=True)
for d in core.available_devices:
    try:
        print("  ", d, core.get_property(d, "FULL_DEVICE_NAME"))
    except Exception:
        pass

tok = AutoTokenizer.from_pretrained(src)
if tok.pad_token_id is None:
    tok.pad_token = tok.eos_token
cands = ["hello", "hej", "jag", "我们", "kan", "看", "can", "själv", "sjalv", "kubectl"]
ctx = "jag är hungrig, but I don't care. 今天我们讨论一下AI的内容，"
texts = [ctx + c for c in cands]


def bench(device, ov_config=None):
    print(f"\n== {device} {ov_config or ''}", flush=True)
    t0 = time.time()
    model = OVModelForCausalLM.from_pretrained(ir, device=device, ov_config=ov_config or {}, compile=True)
    print(f"   load+compile {time.time()-t0:.1f} s", flush=True)
    ids = tok(texts, return_tensors="pt", padding=True)
    with torch.inference_mode():
        for i in range(4):
            t = time.time()
            out = model(**ids)
            dt = (time.time() - t) * 1000
            print(f"   score batch{len(texts)} x {ids['input_ids'].shape[1]} tok: {dt:6.1f} ms" + ("  (warm-up)" if i == 0 else ""), flush=True)
        g = tok(ctx, return_tensors="pt")
        for i in range(2):
            t = time.time()
            model.generate(**g, max_new_tokens=8, do_sample=False)
            print(f"   generate 8 tokens: {(time.time()-t)*1000:6.1f} ms" + ("  (warm-up)" if i == 0 else ""), flush=True)


for dev, cfg in [("CPU", None), ("GPU", None), ("NPU", None), ("NPU", {"NPU_USE_NPUW": "YES", "NPUW_LLM": "YES"})]:
    if dev not in core.available_devices:
        print(f"\n== {dev}: not available")
        continue
    try:
        bench(dev, cfg)
    except Exception as e:
        print(f"   FAILED: {type(e).__name__}: {str(e)[:600]}")
        traceback.print_exc(limit=1)

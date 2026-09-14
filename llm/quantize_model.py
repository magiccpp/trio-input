"""One-time: build the int8 (dynamic) CPU model file so the server never has to hold
fp32 weights. Output: llm/models/<name>-int8.pt (torch.save of the quantized module).

usage: python llm/quantize_model.py [model_dir]
"""
import gc
import os
import sys
import warnings

import torch
from transformers import AutoModelForCausalLM

src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "Qwen3-0.6B")
dst = src.rstrip("\\/") + "-int8.pt"
torch.backends.quantized.engine = "onednn" if "onednn" in torch.backends.quantized.supported_engines else torch.backends.quantized.engine
print("engine:", torch.backends.quantized.engine)

model = AutoModelForCausalLM.from_pretrained(src, dtype=torch.bfloat16, low_cpu_mem_usage=True).eval()
from torch.ao.nn.quantized.dynamic import Linear as QLinear
n = 0
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    for name, mod in list(model.named_modules()):
        for cn, child in list(mod.named_children()):
            if isinstance(child, torch.nn.Linear):
                child = child.float()
                child.qconfig = torch.ao.quantization.default_dynamic_qconfig
                setattr(mod, cn, QLinear.from_float(child))
                del child
                n += 1
                if n % 40 == 0:
                    gc.collect()
for p in model.parameters():                      # norms -> fp32, big embedding stays bf16
    if p.dtype == torch.bfloat16 and p.numel() < 10_000_000:
        p.data = p.data.float()
print(f"quantized {n} Linear layers")
torch.save(model, dst)
print("wrote", dst, f"{os.path.getsize(dst)/2**20:.0f} MB")

"""Where does the helper's host memory go on an iGPU? usage: python nuc2_loadtest.py [plain|trim|devmap]"""
import ctypes
import gc
import os
import sys

import torch
from transformers import AutoModelForCausalLM

mode = sys.argv[1] if len(sys.argv) > 1 else "plain"
MODEL = os.path.expanduser("~/trilingual-llm/Qwen3-0.6B")


def rss():
    d = {}
    for line in open("/proc/self/status"):
        if line.startswith(("RssAnon", "RssFile", "RssShmem")):
            d[line.split(":")[0]] = int(line.split()[1]) // 1024
    return d


print(mode, "start", rss())
if mode == "devmap":
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, device_map="xpu").eval()
else:
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16, low_cpu_mem_usage=True).to("xpu").eval()
torch.xpu.synchronize()
print(mode, "loaded", rss(), "xpu alloc MB", torch.xpu.memory_allocated() // 2**20)
if mode == "trim":
    gc.collect()
    ctypes.CDLL("libc.so.6").malloc_trim(0)
    print(mode, "trimmed", rss())
with torch.inference_mode():
    x = torch.randint(0, 1000, (10, 40), device="xpu")
    model(input_ids=x).logits.float().sum().item()
torch.xpu.empty_cache()
print(mode, "after forward", rss(), "reserved MB", torch.xpu.memory_reserved() // 2**20)

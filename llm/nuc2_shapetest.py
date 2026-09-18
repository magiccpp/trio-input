"""Does host memory on the iGPU grow with the number of distinct input shapes?
usage: python nuc2_shapetest.py [free|bucket]"""
import os
import random
import sys

import torch
from transformers import AutoModelForCausalLM

mode = sys.argv[1] if len(sys.argv) > 1 else "free"
model = AutoModelForCausalLM.from_pretrained(os.path.expanduser("~/trilingual-llm/Qwen3-0.6B"), dtype=torch.bfloat16,
                                             low_cpu_mem_usage=True).to("xpu").eval()


def anon():
    for line in open("/proc/self/status"):
        if line.startswith("RssAnon"):
            return int(line.split()[1]) // 1024


random.seed(1)
with torch.inference_mode():
    for i in range(121):
        b, t = random.randint(2, 11), random.randint(4, 70)
        if mode == "bucket":
            b, t = 12 if b > 6 else 6, -(-t // 24) * 24
        x = torch.randint(0, 1000, (b, t), device="xpu")
        model(input_ids=x).logits[:, -1].float().sum().item()
        torch.xpu.empty_cache()
        if i % 30 == 0:
            print(mode, i, "RssAnon MB", anon(), "reserved", torch.xpu.memory_reserved() // 2**20, flush=True)

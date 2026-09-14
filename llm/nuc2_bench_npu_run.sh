#!/bin/bash
cd ~/trilingual-llm
export PATH="$HOME/trilingual-llm/.venv-ov/bin:$PATH"
tr -d '\r' < bench_npu_src.py > bench_npu.py
.venv-ov/bin/python -u bench_npu.py > bench_npu.log 2>&1
cat bench_npu.log

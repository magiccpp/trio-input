#!/bin/bash
cd ~/trilingual-llm
export PATH="$HOME/trilingual-llm/.venv-ov/bin:$PATH"
.venv-ov/bin/python -u bench.py > bench_ov.log 2>&1
tail -n 70 bench_ov.log

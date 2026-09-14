#!/bin/bash
# Start the LLM helper on nuc2 (Intel Arc iGPU via torch XPU) and probe it.
cd ~/trilingual-llm
for p in $(pgrep -f "llm_server.py"); do [ "$p" != "$$" ] && kill "$p" 2>/dev/null; done
sleep 1
export HF_HUB_OFFLINE=1 DEVICE=auto QUANT=int8 MODEL=$HOME/trilingual-llm/Qwen3-0.6B PORT=8791
setsid nohup .venv/bin/python -u llm_server.py > llm_server.log 2>&1 < /dev/null &
for i in $(seq 1 60); do
  sleep 2
  if grep -q "serving on" llm_server.log; then break; fi
done
grep -E "device order|selected|ready|serving|Error|error" llm_server.log | head -8
.venv/bin/python probe_llm.py http://127.0.0.1:8791

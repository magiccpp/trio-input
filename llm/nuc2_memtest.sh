#!/bin/bash
# A/B on nuc2 (Intel Arc iGPU, torch XPU): how much shared memory does the helper keep
# with and without handing the allocator cache back?  usage: bash nuc2_memtest.sh
cd ~/trilingual-llm
for mode in 0 1; do
  for p in $(pgrep -f "llm_server.py"); do [ "$p" != "$$" ] && kill "$p" 2>/dev/null; done
  sleep 2
  export HF_HUB_OFFLINE=1 DEVICE=auto MODEL=$HOME/trilingual-llm/Qwen3-0.6B PORT=8791 FREE_CACHE=$mode
  setsid nohup .venv/bin/python -u llm_server.py > llm_server.log 2>&1 < /dev/null &
  for i in $(seq 1 60); do sleep 2; grep -q "serving on" llm_server.log && break; done
  echo "=== FREE_CACHE=$mode  $(grep -E 'selected' llm_server.log | head -1)"
  free -m | awk 'NR==2{print "system used MB before:", $3, " shared:", $5}'
  .venv/bin/python stress_vram.py http://127.0.0.1:8791
  free -m | awk 'NR==2{print "system used MB after: ", $3, " shared:", $5}'
done
for p in $(pgrep -f "llm_server.py"); do [ "$p" != "$$" ] && kill "$p" 2>/dev/null; done

#!/bin/bash
# Intel GPU (XPU) test environment on nuc2. Run: bash nuc2_setup.sh
cd ~/trilingual-llm
for p in $(pgrep -f "pip install" ); do [ "$p" != "$$" ] && kill "$p" 2>/dev/null; done
sleep 1
[ -x .venv/bin/python ] || python3 -m venv .venv
setsid nohup bash -c '
  .venv/bin/pip install --progress-bar off torch --index-url https://download.pytorch.org/whl/xpu &&
  .venv/bin/pip install --progress-bar off transformers &&
  .venv/bin/python -c "import torch; print(\"torch\", torch.__version__, \"xpu:\", torch.xpu.is_available(), torch.xpu.get_device_name(0) if torch.xpu.is_available() else None)"
' > pip_torch.log 2>&1 < /dev/null &
echo "started; log: ~/trilingual-llm/pip_torch.log"

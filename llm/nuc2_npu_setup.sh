#!/bin/bash
# nuc2: OpenVINO toolchain for the NPU / iGPU / CPU comparison (separate venv).
cd ~/trilingual-llm
[ -x .venv-ov/bin/python ] || python3 -m venv .venv-ov
setsid nohup bash -c '
  .venv-ov/bin/pip install --progress-bar off -U pip &&
  .venv-ov/bin/pip install --progress-bar off "openvino>=2025.2" "optimum-intel[openvino]" nncf transformers torch --extra-index-url https://download.pytorch.org/whl/cpu &&
  .venv-ov/bin/python -c "import openvino as ov; c=ov.Core(); print(\"OpenVINO\", ov.__version__, \"devices:\", c.available_devices)"
' > ov_setup.log 2>&1 < /dev/null &
echo "started; log: ~/trilingual-llm/ov_setup.log"

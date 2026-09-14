# Third-party components

| Component | Where | License |
|---|---|---|
| librime (`engine/rime.dll`, from Weasel 0.17.4) | `engine/` | GPL-3.0 (`engine/LICENSE.txt`) — source: https://github.com/rime/librime |
| 朙月拼音 dictionary and schemas (`luna_pinyin.*`, `essay.txt`, `pinyin.yaml`, …) | `engine/data/` | GPL-3.0 / CC-BY 4.0 — https://github.com/rime/rime-prelude, rime-luna-pinyin, rime-essay |
| OpenCC conversion tables | `engine/data/opencc/` | Apache-2.0 — https://github.com/BYVoid/OpenCC |
| FrequencyWords (OpenSubtitles 2016/2018 word lists, en / sv / zh_cn) | `train/data/` | CC-BY-SA 4.0 — https://github.com/hermitdave/FrequencyWords |
| Qwen3-0.6B (downloaded by `install.ps1`) | `llm/models/` | Apache-2.0 — https://huggingface.co/Qwen/Qwen3-0.6B |
| pypinyin | Python dependency | MIT |
| PyTorch, transformers | Python dependencies | BSD-3 / Apache-2.0 |

Because librime is bundled, this repository as a whole is distributed under GPL-3.0 (see `LICENSE`).

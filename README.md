# trio-input — 中文 / English / Svenska in one input, no switching

Type pinyin, English and Swedish in a single input mode. A small character n-gram model
plus a local LLM (Qwen3-0.6B, CPU or GPU, ≈2 GB RAM) decide which language you mean and
rank the candidates; the LLM also predicts the next few words (Tab to accept). It learns
from what you pick and offers to retrain itself.

```
今天我们讨论一下AI的内容，and then我们去吃饭。jag är hungrig, don't care, tack så mycket
```
— typed as `jintian women taolun yixia AI de neirong , and then women qu chifan . jag 'r hungrig ...`
on a plain US keyboard layout, never touching a language switch.

This is a **standalone prototype**: a local web page emulates the input method. Nothing is
registered with Windows. (A RIME/Weasel schema version of the same idea lives in `rime/`.)

## Install (Windows 10/11 x64) — release v1.0.0

```powershell
git clone https://github.com/magiccpp/trio-input.git
cd trio-input
powershell -ExecutionPolicy Bypass -File install.ps1      # add -Backend cpu to force CPU
```

The installer sets up `uv`, two Python 3.12 environments, the PyTorch build matching your
GPU (NVIDIA → CUDA, Intel → XPU, otherwise CPU), downloads the model files from the
[release](https://github.com/magiccpp/trio-input/releases) (≈1.2 GB for CPU, +1.5 GB for GPU)
and puts a **Trio Input** shortcut on the desktop. Then:

```powershell
start.ps1        # starts the LLM helper + UI and opens http://127.0.0.1:8766
```

Requirements: Windows x64, ~4 GB disk, ~2.5 GB free RAM (CPU mode), internet for the install only.

## Using it

| Key | Action |
|---|---|
| letters | compose; candidates appear with a language tag (zh / en / sv) |
| `Space` | commit candidate 1 · `1`–`9` pick another · `←`/`→` move selection |
| `Tab` | accept the next predicted word (grey ghost text); repeat to go further |
| `Enter` | commit exactly what you typed (names, URLs) |
| `Shift`+letter | start a verbatim word (`AI`, `Beijing`) |
| `'` `;` `[` | ä ö å — the physical ä/ö/å keys of a Swedish keyboard under the US layout; typed diacritics are a hard constraint (`'r` → är, never år). `don't` stays available next to `donät`. |
| `, . ? !` | follow the previous word: ，。after 汉字, `, .` after Latin |
| `Esc` | clear the composition |

The best candidate of every language is always within the first five, so a wrong guess is
one digit away.

**Spelling**: a Latin word that matches nothing (no exact word, no completion) gets
corrections within one edit — two for longer words — tagged `fix`: `beleve` → believe,
`recieved` → received, `sjlav` → själv. The literal word stays as candidate 2 (or Enter).

### Learning and retraining
Every commit is logged (`proto/data/selections.jsonl`). Words you pick are promoted
immediately for that input in the same surrounding language (★ tag). After 50 corrections
or 300 selections the UI offers **Retrain model now**: the n-gram model is re-fitted with
your selections mixed in (~10 s) and hot-reloaded.

## How it works

```
typed ascii ─► char n-gram language model (zh/en/sv) + context (last words, script mix)
            ─► exact-word frequency boosts for zh (的/是/我们), en (the/and), sv (jag/och)
            ─► rime.dll (朙月拼音) ─► 汉字 candidates
            ─► EN / SV prefix dictionaries (SV codes ASCII-folded: sjalv → själv)
            ─► raw typed word when it is in no dictionary (kubectl, names)
            ─► [LLM] score candidates that render the whole input:
                 log p(context+cand) − log p(context)  + language prior + frequency/rank prior
            ─► [LLM] predict-ahead: greedy 8-token continuation → ghost text
```

* `proto/app.py` — backend (stdlib HTTP, port 8766); `proto/static/index.html` — UI.
* `proto/llm_server.py` — LLM helper (port 8791): `/score`, `/predict`, `/convert`.
  Device order NVIDIA CUDA → Intel XPU → CPU; CPU uses a pre-quantized int8 file
  (`llm/quantize_model.py`) so the process stays ≈2.2 GB.
* `proto/rime_engine.py` — ctypes wrapper for the bundled librime (`engine/`).
* `train/` — builds the dictionaries (`build_dicts.py`, `build_zh_freq.py`) and the
  language model (`train_langid.py`, also used by retrain).

Measured on a Xeon W-2235 (CPU int8): ≈100 ms per keystroke with the LLM, ≈10 ms without;
43-case evaluation (`proto/eval_proto.py`) 41–42/43 either way, the remaining misses being
genuinely ambiguous two-letter words. Intel Arc iGPU (Core Ultra 7): ≈120 ms. RTX 3090: ≈45 ms.

## Development

```powershell
train\.venv\Scripts\python.exe proto\eval_proto.py       # accuracy with/without LLM
train\.venv\Scripts\python.exe proto\probe_case.py "I would " like   # inspect one case
train\.venv\Scripts\python.exe proto\test_learning.py    # selection log + retrain loop
python train\build_dicts.py; python train\build_zh_freq.py; python train\train_langid.py
```

`rime/` contains the earlier RIME/Weasel schema (Lua ranking filter) — the same detection
inside a real system IME; see `rime/README-weasel.md`.

## License
GPL-3.0 (librime is bundled). Third-party notices: `THIRD_PARTY.md`.

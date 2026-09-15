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

It comes as a **real Windows input method** (Text Services Framework, via
[PIME](https://github.com/EasyIME/PIME)): switch to *Trio Input 中/EN/SV* with Win+Space and
type in any application. The same engine also drives a local web page
(http://127.0.0.1:8766) that shows the language probabilities, the learning status and the
retrain button. (A RIME/Weasel schema version of the same idea lives in `rime/`.)

## Install (Windows 10/11 x64)

**Easiest**: download `TrioInput-Setup-1.0.1.exe` from the
[latest release](https://github.com/magiccpp/trio-input/releases/latest) and run it.
No git, no Python, no admin rights. The setup installs into `%LOCALAPPDATA%\TrioInput`,
downloads the Python runtime and the language model (≈1.7 GB, CPU) during installation,
and creates **Trio Input** in the Start Menu (optionally on the desktop / at login).
The setup detects your GPU and pre-selects the matching runtime: NVIDIA → CUDA (~4.5 GB
download), Intel Arc / Core Ultra iGPU → XPU (~3.2 GB), otherwise CPU (~1.7 GB); you can
override it on the components page. Start Trio Input → the input page opens at
http://127.0.0.1:8766. Uninstall from Windows Settings → Apps.
Unattended: `TrioInput-Setup-1.0.1.exe /VERYSILENT /GPU=auto|cpu|xpu|cuda`.

Requirements: Windows 10/11 x64, ~4 GB disk, ~2.5 GB free RAM, internet during install only.

**From source** (developers, or NVIDIA GPU):

```powershell
git clone https://github.com/magiccpp/trio-input.git
cd trio-input
powershell -ExecutionPolicy Bypass -File install.ps1      # picks CUDA / XPU / CPU torch, downloads the model
start.ps1                                                # LLM helper + UI, opens the browser
```

Build the installer yourself: `build\make_runtime.ps1 -Backend cpu|xpu` (portable Python +
torch bundles) and `ISCC.exe installer\TrioInput.iss` (Inno Setup 6).

## System-wide input method (PIME)

`ime/trio` is the PIME module: PIME's `PIMETextService.dll` is the TSF text service that
Windows loads into every application; it forwards keys over a pipe to PIME's Python
server, where `trio_ime.py` runs the same key rules as the web page and asks the
trio-input backend (`proto/app.py`, started on demand) for candidates.

```powershell
# once: PIME 1.3.0 (https://github.com/EasyIME/PIME/releases, PIME-1.3.0-stable-setup.exe /S)
powershell -ExecutionPolicy Bypass -File ime\install_ime.ps1        # copies the module, registers (UAC)
powershell -ExecutionPolicy Bypass -File ime\install_ime.ps1 -Remove
```

Then add *Trio Input 中/EN/SV* under Settings → Time & Language → Language → 中文(简体) →
Keyboards (or just Win+Space). Automated check: `ime\test_notepad.ps1` switches to Trio,
types a mixed sentence into Notepad through the IME and prints what arrived.

In the IME, keystrokes use the fast path (~10 ms); **Space** re-asks with the LLM before
committing (~100 ms), digits pick from the shown list, **Enter** commits what you typed,
**Tab** accepts the predicted next word. The space after a Latin word is deferred until the
next word so Chinese and punctuation can follow without a gap.

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

Intel iGPU vs NPU (Core Ultra 7 155H, OpenVINO 2026.3, Qwen3-0.6B int8, the `/score`
workload = 10 candidates × 23 tokens in one batch, and an 8-token `/predict`):

| device | score batch | generate 8 tokens | note |
|---|---|---|---|
| iGPU (Arc), OpenVINO | 195 ms | 340 ms | |
| iGPU (Arc), torch XPU bf16 | ≈120 ms | – | what `llm_server.py` uses |
| CPU, OpenVINO int8 | 420 ms | 205 ms | |
| NPU, OpenVINO NPUW LLM pipeline | 5 200 ms (10 sequential prefills) | 3 400 ms | only path that compiles; batched/dynamic shapes rejected |

The NPU is built for long single-stream decoding with static shapes; this input method's
workload (many short batched prefills per keystroke) runs 15–25× slower there than on the
iGPU. Use the iGPU (`DEVICE=xpu`) or the CPU.

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

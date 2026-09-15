# -*- coding: utf-8 -*-
"""Trio Input — PIME (Windows TSF) frontend for the trio-input engine.

PIME renders the composition and candidate window inside any application; this module
holds the keyboard state machine (the same rules as the web prototype) and asks the
trio-input backend (proto/app.py on 127.0.0.1:8766) for candidates. The backend is
started on demand from the installed app directory.

Keys: letters compose; Space commits the best guess (LLM-ranked); 1-9 pick; Enter commits
what you typed; Esc clears; ' ; [ are ä ö å (US layout); Shift+letter = verbatim word;
punctuation follows the previous word; Tab accepts the predicted next word.
"""
import json
import os
import re
import subprocess
import time
import urllib.request

from keycodes import *  # noqa: F401,F403  (VK_* constants from PIME)
from textService import TextService

BACKEND = "http://127.0.0.1:8766"
CJK = re.compile(u"[\u4e00-\u9fff]")
NORDIC = {"'": u"ä", ";": u"ö", "[": u"å", '"': u"Ä", ":": u"Ö", "{": u"Å",
          u"å": u"å", u"ä": u"ä", u"ö": u"ö", u"Å": u"Å", u"Ä": u"Ä", u"Ö": u"Ö"}
FULL = {",": u"，", ".": u"。", "?": u"？", "!": u"！", ":": u"：", ";": u"；", "(": u"（", ")": u"）"}
UNIT_RE = re.compile(u"\\s*[A-Za-z\u00c5\u00c4\u00d6\u00e5\u00e4\u00f6'\u2019-]+|\\s*[\u4e00-\u9fff]+|\\s*[0-9][0-9.,:%/-]*|\\s*\\S")

CANDIDATE_APP_DIRS = [
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "TrioInput"),
    r"C:\claude\trilingual-ime",
]


def _post(path, payload, timeout=1.5):
    req = urllib.request.Request(BACKEND + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _backend_up():
    try:
        urllib.request.urlopen(BACKEND + "/status", timeout=0.4).read()
        return True
    except Exception:
        return False


def _start_backend():
    for d in CANDIDATE_APP_DIRS:
        script = os.path.join(d, "start.ps1")
        if os.path.isfile(script):
            try:
                subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                                  "-File", script, "-NoBrowser"], cwd=d, creationflags=0x08000000)
            except Exception:
                pass
            return d
    return None


class TrioTextService(TextService):
    def __init__(self, client):
        TextService.__init__(self, client)
        self.comp = u""        # what the engine sees (ä ö å already mapped)
        self.raw = u""         # literal keys typed
        self.cands = []        # candidate dicts from the backend
        self.sel = 0
        self.verbatim = False
        self.sv_hint = False
        self.text = u""        # our own record of recent commits = language context
        self.auto_spaced = False
        self.ghost = []        # predicted next units (Tab)
        self.sid = str(int(time.time() * 1000))
        self.seq = 0
        self.backend_checked = 0.0
        self.autospace = True

    # ------------------------------------------------------------------ lifecycle
    def onActivate(self):
        TextService.onActivate(self)
        self.setSelKeys("123456789")
        self.customizeUI(candFontSize=16, candPerRow=9, candUseCursor=True)
        self.ensure_backend()

    def onDeactivate(self):
        TextService.onDeactivate(self)
        self.reset_comp()

    def onCompositionTerminated(self, forced):
        TextService.onCompositionTerminated(self, forced)
        if forced:
            self.reset_comp()

    def ensure_backend(self):
        now = time.time()
        if now - self.backend_checked < 5:
            return
        self.backend_checked = now
        if not _backend_up():
            _start_backend()

    # ------------------------------------------------------------------ helpers
    def reset_comp(self):
        self.comp = u""
        self.raw = u""
        self.cands = []
        self.sel = 0
        self.verbatim = False
        self.sv_hint = False
        self.setCompositionString(u"")
        self.setCompositionCursor(0)
        self.setCandidateList([])
        self.setShowCandidates(False)

    def show(self):
        self.setCompositionString(self.comp)
        self.setCompositionCursor(len(self.comp))
        if self.verbatim or not self.cands:
            self.setCandidateList([])
            self.setShowCandidates(False)
        else:
            self.setCandidateList([c["text"] for c in self.cands[:9]])
            self.setCandidateCursor(self.sel)
            self.setShowCandidates(True)

    def refresh(self, use_llm=False):
        if not self.comp or self.verbatim:
            self.cands = []
            return
        self.seq += 1
        try:
            j = _post("/compose", {"input": self.comp, "raw": self.raw, "context": self.text[-300:],
                                   "sv_hint": self.sv_hint, "seq": self.seq, "sid": self.sid, "use_llm": use_llm},
                      timeout=3.0 if use_llm else 1.0)
            self.cands = j.get("candidates", [])
            self.last_primary = j.get("primary")
        except Exception:
            self.ensure_backend()
            self.cands = [{"text": self.raw, "lang": "en", "source": "raw"}]
        self.sel = 0

    def learn(self, cand, index, ctx_before):
        try:
            _post("/select", {"text": cand["text"], "lang": cand.get("lang"), "index": index, "source": cand.get("source"),
                              "input": self.comp, "raw": self.raw, "context": ctx_before[-200:],
                              "primary": getattr(self, "last_primary", None),
                              "shown": [c["text"] for c in self.cands[:5]]}, timeout=0.5)
        except Exception:
            pass

    def commit_text(self, s):
        self.setCommitString(s)
        self.text = (self.text + s)[-1000:]

    def commit(self, index):
        ctx_before = self.text
        if self.verbatim:
            self.commit_text(self.raw + (u" " if self.autospace else u""))
            self.auto_spaced = self.autospace
        elif 0 <= index < len(self.cands):
            c = self.cands[index]
            out = c["text"]
            if c.get("lang") == "zh" and self.auto_spaced and self.text.endswith(u" "):
                # Chinese follows Latin without the automatic space: we cannot delete
                # committed text, so we simply do not add another space afterwards
                pass
            if c.get("lang") != "zh" and self.autospace:
                out += u" "
                self.auto_spaced = True
            else:
                self.auto_spaced = False
            self.commit_text(out)
            self.learn(c, index, ctx_before)
        else:
            self.commit_text(self.raw + (u" " if self.autospace else u""))
        self.reset_comp()
        self.predict()

    def predict(self):
        self.ghost = []
        try:
            j = _post("/predict", {"context": self.text[-400:], "seq": self.seq, "sid": self.sid}, timeout=2.5)
            self.ghost = j.get("units", [])
        except Exception:
            pass

    def accept_ghost(self):
        if not self.ghost:
            return False
        u = self.ghost.pop(0)
        if re.match(u"^[A-Za-z\u00c5\u00c4\u00d6\u00e5\u00e4\u00f6]", u) and re.search(u"[A-Za-z\u00c5\u00c4\u00d6\u00e5\u00e4\u00f60-9]$", self.text):
            u = u" " + u
        if u.startswith(u" ") and (self.text == u"" or self.text.endswith(u" ") or CJK.search(self.text[-1:])):
            u = u.lstrip()
        self.commit_text(u)
        self.auto_spaced = False
        if not self.ghost:
            self.predict()
        return True

    # ------------------------------------------------------------------ keys
    @staticmethod
    def _down(keyEvent, vk):
        return bool(keyEvent.keyStates[vk] & 0x80)

    def filterKeyDown(self, keyEvent):
        if not self.keyboardOpen:
            return False
        if self._down(keyEvent, VK_CONTROL) or self._down(keyEvent, VK_MENU) or self._down(keyEvent, VK_LWIN) or self._down(keyEvent, VK_RWIN):
            return False
        kc, ch = keyEvent.keyCode, keyEvent.charCode
        if self.isComposing():
            return True                          # every key is ours while composing
        if kc in (VK_SPACE, VK_RETURN, VK_ESCAPE, VK_BACK, VK_UP, VK_DOWN, VK_LEFT, VK_RIGHT, VK_SHIFT, VK_CAPITAL):
            return kc == VK_TAB                  # let the app have them when idle (Tab handled below)
        if kc == VK_TAB:
            return bool(self.ghost)
        if 32 < ch < 127:
            c = chr(ch)
            return c.isalpha() or c in NORDIC or c in FULL   # start composing / smart punctuation
        return False

    def onKeyDown(self, keyEvent):
        kc, ch = keyEvent.keyCode, keyEvent.charCode
        c = chr(ch) if 0 < ch < 0x110000 else u""

        if kc == VK_TAB:
            if self.comp:
                self.refresh(use_llm=False)
                i = next((i for i, x in enumerate(self.cands) if i > 0 and x.get("source") in ("dict", "spell")), -1)
                self.commit(i if i > 0 else self.sel)
            else:
                self.accept_ghost()
                self.show()
            return True
        self.ghost = []

        if kc == VK_ESCAPE:
            self.reset_comp()
            return True
        if kc == VK_BACK:
            if self.comp:
                self.comp, self.raw = self.comp[:-1], self.raw[:-1]
                if not self.comp:
                    self.reset_comp()
                else:
                    self.refresh()
                    self.show()
                return True
            return False
        if kc == VK_RETURN:
            if self.comp:
                self.commit_text(self.raw + (u" " if self.autospace and not self.verbatim else u""))
                self.reset_comp()
                return True
            return False
        if kc == VK_SPACE:
            if self.comp:
                if not self.verbatim:
                    self.refresh(use_llm=True)      # the LLM's verdict for the commit
                self.commit(self.sel)
                return True
            return False
        if kc in (VK_LEFT, VK_UP, VK_RIGHT, VK_DOWN) and self.cands:
            n = min(9, len(self.cands))
            self.sel = (self.sel + (1 if kc in (VK_RIGHT, VK_DOWN) else -1)) % n
            self.show()
            return True
        if c.isdigit() and self.comp and not self.verbatim:
            i = int(c) - 1
            if 0 <= i < len(self.cands):
                self.commit(i)
            return True
        if c and c.isalpha() and c.isascii():
            if not self.comp and c.isupper():
                self.verbatim = True
            self.comp += c
            self.raw += c
            self.refresh()
            self.show()
            return True
        if c in NORDIC:
            if not self.comp and NORDIC[c].isupper():
                self.verbatim = True
            self.comp += NORDIC[c]
            self.raw += c
            self.sv_hint = True
            if not self.verbatim:
                self.refresh()
            self.show()
            return True
        if c in FULL:
            if self.comp:
                if not self.verbatim:
                    self.refresh(use_llm=True)
                self.commit(self.sel)
            last = self.text.rstrip()[-1:]
            if CJK.search(last):
                self.commit_text(FULL[c])
            else:
                self.commit_text(c)
            return True
        if self.comp:
            # any other printable key ends the composition and is passed through as typed
            self.commit(self.sel)
            self.commit_text(c)
            return True
        return False

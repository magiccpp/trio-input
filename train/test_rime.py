"""Drive librime (Weasel's rime.dll) directly to test the trilingual schema.

usage: python test_rime.py <user_dir> [inputs...]
Each input is a sequence of keys; use '{sp}' for space, '{ret}' for Return,
'{bs}' for BackSpace. Non-ascii letters (å ä ö) are sent as X11 keysyms.
"""
from __future__ import annotations

import ctypes as C
import os
import sys
import time

WEASEL = r"C:\Program Files\Rime\weasel-0.17.4"
os.add_dll_directory(WEASEL)
rime = C.CDLL(os.path.join(WEASEL, "rime.dll"))

Bool = C.c_int
RimeSessionId = C.c_size_t


class RimeTraits(C.Structure):
    _fields_ = [
        ("data_size", C.c_int),
        ("shared_data_dir", C.c_char_p),
        ("user_data_dir", C.c_char_p),
        ("distribution_name", C.c_char_p),
        ("distribution_code_name", C.c_char_p),
        ("distribution_version", C.c_char_p),
        ("app_name", C.c_char_p),
        ("modules", C.POINTER(C.c_char_p)),
        ("min_log_level", C.c_int),
        ("log_dir", C.c_char_p),
        ("prebuilt_data_dir", C.c_char_p),
        ("staging_dir", C.c_char_p),
    ]


class RimeComposition(C.Structure):
    _fields_ = [("length", C.c_int), ("cursor_pos", C.c_int), ("sel_start", C.c_int),
                ("sel_end", C.c_int), ("preedit", C.c_char_p)]


class RimeCandidate(C.Structure):
    _fields_ = [("text", C.c_char_p), ("comment", C.c_char_p), ("reserved", C.c_void_p)]


class RimeMenu(C.Structure):
    _fields_ = [("page_size", C.c_int), ("page_no", C.c_int), ("is_last_page", Bool),
                ("highlighted_candidate_index", C.c_int), ("num_candidates", C.c_int),
                ("candidates", C.POINTER(RimeCandidate)), ("select_keys", C.c_char_p)]


class RimeContext(C.Structure):
    _fields_ = [("data_size", C.c_int), ("composition", RimeComposition), ("menu", RimeMenu),
                ("commit_text_preview", C.c_char_p), ("select_labels", C.POINTER(C.c_char_p))]


class RimeCommit(C.Structure):
    _fields_ = [("data_size", C.c_int), ("text", C.c_char_p)]


rime.RimeSetup.argtypes = [C.POINTER(RimeTraits)]
rime.RimeInitialize.argtypes = [C.POINTER(RimeTraits)]
rime.RimeStartMaintenance.argtypes = [Bool]
rime.RimeStartMaintenance.restype = Bool
rime.RimeCreateSession.restype = RimeSessionId
rime.RimeSelectSchema.argtypes = [RimeSessionId, C.c_char_p]
rime.RimeSelectSchema.restype = Bool
rime.RimeProcessKey.argtypes = [RimeSessionId, C.c_int, C.c_int]
rime.RimeProcessKey.restype = Bool
rime.RimeGetContext.argtypes = [RimeSessionId, C.POINTER(RimeContext)]
rime.RimeGetContext.restype = Bool
rime.RimeFreeContext.argtypes = [C.POINTER(RimeContext)]
rime.RimeGetCommit.argtypes = [RimeSessionId, C.POINTER(RimeCommit)]
rime.RimeGetCommit.restype = Bool
rime.RimeFreeCommit.argtypes = [C.POINTER(RimeCommit)]
rime.RimeDestroySession.argtypes = [RimeSessionId]
rime.RimeFinalize.argtypes = []

KEYS = {"{sp}": 0x20, "{ret}": 0xFF0D, "{bs}": 0xFF08, "{esc}": 0xFF1B,
        "å": 0xE5, "ä": 0xE4, "ö": 0xF6, "Å": 0xC5, "Ä": 0xC4, "Ö": 0xD6}


def tokenize(s):
    i = 0
    while i < len(s):
        if s[i] == "{":
            j = s.index("}", i) + 1
            yield KEYS[s[i:j]]
            i = j
        else:
            yield KEYS.get(s[i], ord(s[i]))
            i += 1


def main():
    user_dir = sys.argv[1]
    inputs = sys.argv[2:] or ["nihao", "hello", "hej", "sjalv", "sj\u00e4lv", "woxiangchifan", "and", "tack", "jag{sp}kan{sp}", "hello{sp}world{sp}and{sp}"]
    log_dir = os.path.join(user_dir, "log")
    os.makedirs(log_dir, exist_ok=True)
    t = RimeTraits()
    t.data_size = C.sizeof(RimeTraits) - C.sizeof(C.c_int)
    t.shared_data_dir = os.path.join(WEASEL, "data").encode()
    t.user_data_dir = user_dir.encode()
    t.distribution_name = b"Weasel"
    t.distribution_code_name = b"Weasel"
    t.distribution_version = b"0.17.4"
    t.app_name = b"rime.test"
    t.min_log_level = 0
    t.log_dir = log_dir.encode()
    rime.RimeSetup(C.byref(t))
    rime.RimeInitialize(C.byref(t))
    if rime.RimeStartMaintenance(0):
        rime.RimeJoinMaintenanceThread()
    sid = rime.RimeCreateSession()
    ok = rime.RimeSelectSchema(sid, b"trilingual")
    print("select schema trilingual:", bool(ok))

    for inp in inputs:
        print(f"\n=== {inp!r}")
        for key in tokenize(inp):
            t0 = time.perf_counter()
            rime.RimeProcessKey(sid, key, 0)
            dt = (time.perf_counter() - t0) * 1000
            commit = RimeCommit(); commit.data_size = C.sizeof(RimeCommit) - C.sizeof(C.c_int)
            if rime.RimeGetCommit(sid, C.byref(commit)):
                print(f"  COMMIT: {commit.text.decode('utf-8')!r}")
                rime.RimeFreeCommit(C.byref(commit))
            ctx = RimeContext(); ctx.data_size = C.sizeof(RimeContext) - C.sizeof(C.c_int)
            if rime.RimeGetContext(sid, C.byref(ctx)):
                pre = (ctx.composition.preedit or b"").decode("utf-8", "replace")
                cands = []
                for i in range(ctx.menu.num_candidates):
                    c = ctx.menu.candidates[i]
                    txt = c.text.decode("utf-8", "replace")
                    cm = (c.comment or b"").decode("utf-8", "replace")
                    cands.append(txt + (f"[{cm.strip()}]" if cm.strip() else ""))
                if pre or cands:
                    print(f"  {chr(key) if 32 < key < 127 else hex(key)}: {dt:5.1f}ms  preedit={pre!r}  ->  {'  '.join(cands)}")
                rime.RimeFreeContext(C.byref(ctx))
        # clear any leftover composition
        rime.RimeProcessKey(sid, 0xFF1B, 0)
    rime.RimeDestroySession(sid)
    rime.RimeFinalize()


if __name__ == "__main__":
    main()

"""Thin ctypes wrapper around librime (engine/rime.dll) used only for
pinyin -> hanzi candidates. Fully self-contained: shared data and user
data live under engine/, nothing is registered with Windows."""
from __future__ import annotations

import ctypes as C
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "engine"


class RimeTraits(C.Structure):
    _fields_ = [
        ("data_size", C.c_int), ("shared_data_dir", C.c_char_p), ("user_data_dir", C.c_char_p),
        ("distribution_name", C.c_char_p), ("distribution_code_name", C.c_char_p),
        ("distribution_version", C.c_char_p), ("app_name", C.c_char_p),
        ("modules", C.POINTER(C.c_char_p)), ("min_log_level", C.c_int), ("log_dir", C.c_char_p),
        ("prebuilt_data_dir", C.c_char_p), ("staging_dir", C.c_char_p),
    ]


class RimeComposition(C.Structure):
    _fields_ = [("length", C.c_int), ("cursor_pos", C.c_int), ("sel_start", C.c_int),
                ("sel_end", C.c_int), ("preedit", C.c_char_p)]


class RimeCandidate(C.Structure):
    _fields_ = [("text", C.c_char_p), ("comment", C.c_char_p), ("reserved", C.c_void_p)]


class RimeMenu(C.Structure):
    _fields_ = [("page_size", C.c_int), ("page_no", C.c_int), ("is_last_page", C.c_int),
                ("highlighted_candidate_index", C.c_int), ("num_candidates", C.c_int),
                ("candidates", C.POINTER(RimeCandidate)), ("select_keys", C.c_char_p)]


class RimeContext(C.Structure):
    _fields_ = [("data_size", C.c_int), ("composition", RimeComposition), ("menu", RimeMenu),
                ("commit_text_preview", C.c_char_p), ("select_labels", C.POINTER(C.c_char_p))]


class RimeEngine:
    def __init__(self, schema: str = "luna_pinyin_simp"):
        os.add_dll_directory(str(ENGINE))
        self.rime = r = C.CDLL(str(ENGINE / "rime.dll"))
        r.RimeSetup.argtypes = [C.POINTER(RimeTraits)]
        r.RimeInitialize.argtypes = [C.POINTER(RimeTraits)]
        r.RimeStartMaintenance.argtypes = [C.c_int]
        r.RimeStartMaintenance.restype = C.c_int
        r.RimeCreateSession.restype = C.c_size_t
        r.RimeSelectSchema.argtypes = [C.c_size_t, C.c_char_p]
        r.RimeProcessKey.argtypes = [C.c_size_t, C.c_int, C.c_int]
        r.RimeProcessKey.restype = C.c_int
        r.RimeSimulateKeySequence.argtypes = [C.c_size_t, C.c_char_p]
        r.RimeSimulateKeySequence.restype = C.c_int
        r.RimeGetContext.argtypes = [C.c_size_t, C.POINTER(RimeContext)]
        r.RimeGetContext.restype = C.c_int
        r.RimeFreeContext.argtypes = [C.POINTER(RimeContext)]
        r.RimeClearComposition.argtypes = [C.c_size_t]
        r.RimeDestroySession.argtypes = [C.c_size_t]

        user = ENGINE / "user"
        log = ENGINE / "log"
        user.mkdir(exist_ok=True)
        log.mkdir(exist_ok=True)
        t = self.traits = RimeTraits()
        t.data_size = C.sizeof(RimeTraits) - C.sizeof(C.c_int)
        t.shared_data_dir = str(ENGINE / "data").encode()
        t.user_data_dir = str(user).encode()
        t.distribution_name = b"trilingual-proto"
        t.distribution_code_name = b"trilingual-proto"
        t.distribution_version = b"0.1"
        t.app_name = b"rime.trilingual"
        t.min_log_level = 1
        t.log_dir = str(log).encode()
        r.RimeSetup(C.byref(t))
        r.RimeInitialize(C.byref(t))
        if r.RimeStartMaintenance(0):
            r.RimeJoinMaintenanceThread()
        self.sid = r.RimeCreateSession()
        if not r.RimeSelectSchema(self.sid, schema.encode()):
            raise RuntimeError(f"schema {schema} not available")

    def candidates(self, pinyin: str, limit: int = 12) -> tuple[str, list[str]]:
        """Return (preedit, candidates) for a raw pinyin string."""
        r = self.rime
        r.RimeClearComposition(self.sid)
        if not pinyin or not pinyin.isascii() or not pinyin.isalpha():
            return "", []
        r.RimeSimulateKeySequence(self.sid, pinyin.lower().encode())
        ctx = RimeContext()
        ctx.data_size = C.sizeof(RimeContext) - C.sizeof(C.c_int)
        out, pre = [], ""
        if r.RimeGetContext(self.sid, C.byref(ctx)):
            pre = (ctx.composition.preedit or b"").decode("utf-8", "replace")
            for i in range(min(ctx.menu.num_candidates, limit)):
                out.append(ctx.menu.candidates[i].text.decode("utf-8", "replace"))
            r.RimeFreeContext(C.byref(ctx))
        r.RimeClearComposition(self.sid)
        return pre, out

    def close(self):
        self.rime.RimeDestroySession(self.sid)
        self.rime.RimeFinalize()


if __name__ == "__main__":
    import sys, time
    e = RimeEngine()
    for w in sys.argv[1:] or ["nihao", "woxiangchifan", "zhongguo", "hello"]:
        t0 = time.perf_counter()
        pre, c = e.candidates(w)
        print(f"{w:16s} {(time.perf_counter()-t0)*1000:5.1f}ms  {pre!r} -> {c}")
    e.close()

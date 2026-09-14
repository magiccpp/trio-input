"""Deploy the Weasel user directory in-process via rime.dll (reliable, no GUI).
Run with WeaselServer stopped, then start it again."""
import ctypes as C
import os
import sys

WEASEL = r"C:\Program Files\Rime\weasel-0.17.4"
os.add_dll_directory(WEASEL)
rime = C.CDLL(os.path.join(WEASEL, "rime.dll"))


class RimeTraits(C.Structure):
    _fields_ = [
        ("data_size", C.c_int), ("shared_data_dir", C.c_char_p), ("user_data_dir", C.c_char_p),
        ("distribution_name", C.c_char_p), ("distribution_code_name", C.c_char_p),
        ("distribution_version", C.c_char_p), ("app_name", C.c_char_p),
        ("modules", C.POINTER(C.c_char_p)), ("min_log_level", C.c_int), ("log_dir", C.c_char_p),
        ("prebuilt_data_dir", C.c_char_p), ("staging_dir", C.c_char_p),
    ]


user_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ["APPDATA"], "Rime")
log_dir = os.path.join(os.environ["TEMP"], "rime.deploy")
os.makedirs(log_dir, exist_ok=True)
t = RimeTraits()
t.data_size = C.sizeof(RimeTraits) - C.sizeof(C.c_int)
t.shared_data_dir = os.path.join(WEASEL, "data").encode()
t.user_data_dir = user_dir.encode()
t.distribution_name = b"Weasel"
t.distribution_code_name = b"Weasel"
t.distribution_version = b"0.17.4"
t.app_name = b"rime.deploy"
t.min_log_level = 0
t.log_dir = log_dir.encode()
rime.RimeSetup(C.byref(t))
rime.RimeDeployerInitialize(C.byref(t))
rime.RimeStartMaintenance.argtypes = [C.c_int]
rime.RimeStartMaintenance.restype = C.c_int
ok = rime.RimeStartMaintenance(1)  # full check: rebuild everything that changed
if ok:
    rime.RimeJoinMaintenanceThread()
print("RimeDeploy:", "OK" if ok else "FAILED", "| logs in", log_dir)
rime.RimeFinalize()
sys.exit(0 if ok else 1)

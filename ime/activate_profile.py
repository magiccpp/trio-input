"""Activate (or query) a TSF input-processor profile for the whole session, via
ITfInputProcessorProfileMgr — what Win+Space does, scriptable.

usage: python ime/activate_profile.py [clsid guid langid]      (defaults: Trio Input)
       python ime/activate_profile.py --current                 (print the active profile)
"""
import ctypes
import sys
from ctypes import HRESULT, POINTER, c_uint, c_ulong, c_ushort, c_void_p

import comtypes
from comtypes import COMMETHOD, GUID, IUnknown

CLSID_TF_InputProcessorProfiles = GUID("{33C53A50-F456-4884-B049-85FD643ECFED}")
TRIO_CLSID = GUID("{35F67E9D-A54D-4177-9697-8B0AB71A9E04}")   # PIME text service
TRIO_GUID = GUID("{6B1A4C2E-7D3F-4A5B-9E8C-2F1D0A3B4C5D}")    # Trio language profile
TF_PROFILETYPE_INPUTPROCESSOR = 1
TF_PROFILETYPE_KEYBOARDLAYOUT = 2
TF_IPPMF_DONTCARECURRENTINPUTLANGUAGE = 0x1
TF_IPPMF_FORSESSION = 0x2
TF_IPPMF_ENABLEPROFILE = 0x8


class TF_INPUTPROCESSORPROFILE(ctypes.Structure):
    _fields_ = [("dwProfileType", c_ulong), ("langid", c_ushort), ("clsid", GUID), ("guidProfile", GUID),
                ("catid", GUID), ("hklSubstitute", c_void_p), ("dwCaps", c_ulong), ("hkl", c_void_p), ("dwFlags", c_ulong)]


class ITfInputProcessorProfileMgr(IUnknown):
    _iid_ = GUID("{71C6E74C-0F28-11D8-A82A-00065B84435C}")
    _methods_ = [
        COMMETHOD([], HRESULT, "ActivateProfile", (["in"], c_ulong, "dwProfileType"), (["in"], c_ushort, "langid"),
                  (["in"], POINTER(GUID), "clsid"), (["in"], POINTER(GUID), "guidProfile"), (["in"], c_void_p, "hkl"),
                  (["in"], c_ulong, "dwFlags")),
        COMMETHOD([], HRESULT, "DeactivateProfile", (["in"], c_ulong, "dwProfileType"), (["in"], c_ushort, "langid"),
                  (["in"], POINTER(GUID), "clsid"), (["in"], POINTER(GUID), "guidProfile"), (["in"], c_void_p, "hkl"),
                  (["in"], c_ulong, "dwFlags")),
        COMMETHOD([], HRESULT, "GetProfile", (["in"], c_ulong, "dwProfileType"), (["in"], c_ushort, "langid"),
                  (["in"], POINTER(GUID), "clsid"), (["in"], POINTER(GUID), "guidProfile"), (["in"], c_void_p, "hkl"),
                  (["out"], POINTER(TF_INPUTPROCESSORPROFILE), "pProfile")),
        COMMETHOD([], HRESULT, "EnumProfiles", (["in"], c_ushort, "langid"), (["out"], POINTER(c_void_p), "ppEnum")),
        COMMETHOD([], HRESULT, "ReleaseInputProcessor", (["in"], POINTER(GUID), "rclsid"), (["in"], c_ulong, "dwFlags")),
        COMMETHOD([], HRESULT, "RegisterProfile", (["in"], POINTER(GUID), "rclsid"), (["in"], c_ushort, "langid"),
                  (["in"], POINTER(GUID), "guidProfile"), (["in"], c_void_p, "pchDesc"), (["in"], c_ulong, "cchDesc"),
                  (["in"], c_void_p, "pchIconFile"), (["in"], c_ulong, "cchFile"), (["in"], c_ulong, "uIconIndex"),
                  (["in"], c_void_p, "hklsubstitute"), (["in"], c_ulong, "dwPreferredLayout"), (["in"], c_uint, "bEnabledByDefault"),
                  (["in"], c_ulong, "dwFlags")),
        COMMETHOD([], HRESULT, "UnregisterProfile", (["in"], POINTER(GUID), "rclsid"), (["in"], c_ushort, "langid"),
                  (["in"], POINTER(GUID), "guidProfile"), (["in"], c_ulong, "dwFlags")),
        COMMETHOD([], HRESULT, "GetActiveProfile", (["in"], POINTER(GUID), "catid"), (["out"], POINTER(TF_INPUTPROCESSORPROFILE), "pProfile")),
    ]


GUID_TFCAT_TIP_KEYBOARD = GUID("{34745C63-B2F0-4784-8B67-5E12C8701A31}")


def main():
    comtypes.CoInitialize()
    mgr = comtypes.CoCreateInstance(CLSID_TF_InputProcessorProfiles, interface=ITfInputProcessorProfileMgr)
    if "--current" in sys.argv:
        p = mgr.GetActiveProfile(GUID_TFCAT_TIP_KEYBOARD)
        print("active: type=%d langid=0x%04x clsid=%s profile=%s hkl=%s" % (p.dwProfileType, p.langid, p.clsid, p.guidProfile, p.hkl))
        return
    if "--restore-english" in sys.argv:
        # plain US keyboard layout (hkl 0x04090409)
        mgr.ActivateProfile(TF_PROFILETYPE_KEYBOARDLAYOUT, 0x0409, GUID("{00000000-0000-0000-0000-000000000000}"),
                            GUID("{00000000-0000-0000-0000-000000000000}"), 0x04090409,
                            TF_IPPMF_FORSESSION | TF_IPPMF_DONTCARECURRENTINPUTLANGUAGE)
        print("restored US English keyboard")
        return
    clsid, guid, langid = TRIO_CLSID, TRIO_GUID, 0x0804
    if len(sys.argv) >= 4:
        clsid, guid, langid = GUID(sys.argv[1]), GUID(sys.argv[2]), int(sys.argv[3], 16)
    flags = TF_IPPMF_FORSESSION | TF_IPPMF_DONTCARECURRENTINPUTLANGUAGE
    for a in sys.argv:
        if a.startswith("--flags="):
            flags = int(a.split("=", 1)[1], 0)
    print("ActivateProfile flags=0x%x" % flags)
    mgr.ActivateProfile(TF_PROFILETYPE_INPUTPROCESSOR, langid, clsid, guid, None, flags)
    p = mgr.GetActiveProfile(GUID_TFCAT_TIP_KEYBOARD)
    print("activated; now active: langid=0x%04x clsid=%s profile=%s" % (p.langid, p.clsid, p.guidProfile))


if __name__ == "__main__":
    main()

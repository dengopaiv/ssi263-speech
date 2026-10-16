"""Double speed (bl_board.h bl_set_double_speed): the English Braille Lite 2000 from its warm state, its own switch
turned on (the status menu, then + (dots 3-4-6), answered y), with the emulator's double speed allowed.

    python test_double_speed.py [--firmware DIR] [--lib PATH]

  switch    the firmware sets the Z8S180's CCR bit 7 and the board follows it (double_speed_now 1)
  faster    a typed letter is answered in at most 0.65 of the time it takes at the base clock (the firmware's own
            work, before its first phoneme, runs twice as fast)
  pace      the speech itself keeps its pace: a read line lasts within 3 % of the base clock's (the SSI-263 has
            its own clock)
  base      allowed but never switched on, the unit answers exactly as with double speed off

Control (SSI263_DOUBLE_SPEED_BREAK=1): double speed never allowed -- the switch then changes nothing, and the
"faster" check must fail.
"""
import argparse
import ctypes
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
WINDOWS = sys.platform == "win32"
BREAK = os.environ.get("SSI263_DOUBLE_SPEED_BREAK") == "1"
RATE = 22050
SPACE = 0x40
STATUS, PLUS, YES, EXIT = 0x0C | SPACE, 0x2C, 0x3D, 0x11 | SPACE
LETTERS = (0x13, 0x11, 0x07, 0x07, 0x15)            # h e l l o
READ_LINE = 0x09 | SPACE                            # dots 1-4 chord


class W(ctypes.Structure):
    _fields_ = [("t", ctypes.c_double), ("reg", ctypes.c_int), ("val", ctypes.c_int)]


def load(path):
    lib = ctypes.CDLL(path)
    lib.ssi263_new.restype = ctypes.c_void_p
    lib.ssi263_new.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_double]
    lib.ssi263_default_rom.restype = ctypes.c_void_p
    lib.ssi263_free.argtypes = [ctypes.c_void_p]
    lib.bh_create.restype = ctypes.c_void_p
    lib.bh_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_double, ctypes.c_double,
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_ulonglong, ctypes.c_int,
                              ctypes.c_char_p, ctypes.c_int]
    lib.bh_destroy.argtypes = [ctypes.c_void_p]
    lib.bh_run.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double,
                           ctypes.POINTER(ctypes.POINTER(ctypes.c_double))]
    lib.bh_get_int.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.bh_set_int.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.bh_key.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.bh_writes.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(W))]
    lib.bh_clear_writes.argtypes = [ctypes.c_void_p]
    return lib


def session(lib, fw, st, allow, switch):
    """-> (ccr, double_speed_now, mean letter response s, line speech span s)"""
    params = ctypes.create_string_buffer(lib.ssi263_params_size())
    lib.ssi263_default_params(params)
    chip = lib.ssi263_new(params, lib.ssi263_default_rom(), float(RATE))
    err = ctypes.create_string_buffer(300)
    h = lib.bh_create(fw.encode(), st.encode(), chip, float(RATE), 5000.0, None, None, 0, 0, 1, err, 300)
    if not h:
        sys.exit("host: " + err.value.decode(errors="replace"))
    lib.bh_set_int(h, b"double_speed", allow)
    y = ctypes.POINTER(ctypes.c_double)()
    clock = [0.0]

    def listen(seconds):
        lib.bh_run(h, seconds, 0.0005, ctypes.byref(y))
        clock[0] += seconds

    def loads():
        wp = ctypes.POINTER(W)()
        n = lib.bh_writes(h, ctypes.byref(wp))
        return [wp[i].t for i in range(n) if wp[i].reg == 0 and wp[i].val & 0x3F]

    listen(12.0)                                    # the greeting
    if switch:
        for key, secs in ((STATUS, 3.5), (PLUS, 3.0), (YES, 2.5), (EXIT, 1.5)):
            lib.bh_key(h, key)
            listen(secs)
    ccr, now = lib.bh_get_int(h, b"ccr") & 0xFF, lib.bh_get_int(h, b"double_speed_now")
    waits = []
    for key in LETTERS:
        lib.bh_clear_writes(h)
        t0 = clock[0]
        lib.bh_key(h, key)
        listen(1.2)
        t = loads()
        waits.append(t[0] - t0 if t else 9.9)
    lib.bh_clear_writes(h)
    lib.bh_key(h, READ_LINE)
    listen(3.0)
    t = loads()
    span = t[-1] - t[0] if len(t) > 1 else 0.0
    lib.bh_destroy(h)
    lib.ssi263_free(chip)
    return ccr, now, sum(waits) / len(waits), span


def main():
    arch = "x64" if struct.calcsize("P") == 8 else "x86"
    ap = argparse.ArgumentParser()
    ap.add_argument("--firmware", default=os.environ.get("SSI263_FIRMWARE") or os.path.join(REPO, "firmware", "blazie"))
    ap.add_argument("--lib", default=os.path.join(REPO, "build", "win", arch, "ssi263speech.dll") if WINDOWS
                    else os.path.join(REPO, "build", "linux", "libssi263speech.so"))
    a = ap.parse_args()
    fw, st = os.path.join(a.firmware, "BL2ENG.BNS"), os.path.join(a.firmware, "bl2_2003_warm.state")
    if not (os.path.isfile(fw) and os.path.isfile(st)):
        print("skip: BL2ENG.BNS and bl2_2003_warm.state are not in %s" % a.firmware)
        return
    lib = load(a.lib)
    bad = 0

    def report(ok, what):
        nonlocal bad
        print("%-4s %s" % ("ok" if ok else "FAIL", what))
        bad += not ok

    base = session(lib, fw, st, 0, True)
    fast = session(lib, fw, st, 0 if BREAK else 1, True)
    idle = session(lib, fw, st, 1, False)
    report(fast[0] == 0x80 and fast[1] == 1,
           "switch   the firmware's switch: CCR %02X, the board at double speed %d (want 80, 1)" % fast[:2])
    report(fast[2] <= 0.65 * base[2],
           "faster   a letter answered in %.0f ms, %.0f ms at the base clock (want at most 0.65 of it)"
           % (fast[2] * 1000, base[2] * 1000))
    report(abs(fast[3] - base[3]) <= 0.03 * base[3],
           "pace     a read line's speech lasts %.3f s, %.3f s at the base clock (within 3 %%)" % (fast[3], base[3]))
    plain = session(lib, fw, st, 0, False)
    report(idle[1] == 0 and abs(idle[2] - plain[2]) < 1e-9 and abs(idle[3] - plain[3]) < 1e-9,
           "base     allowed but not switched on: %.1f ms and %.3f s, as with it off (%.1f ms, %.3f s)"
           % (idle[2] * 1000, idle[3], plain[2] * 1000, plain[3]))
    print("double speed: every check passed" if not bad else "double speed: %d FAILED" % bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

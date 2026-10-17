"""The Sounding Board as a voice (voices.c's speakout:soundingboard, 0.8.5) through the voice API every platform uses:
listed, available only with its two drivers, made, and speaking the Speak-Out's voice: its front end is the Speak-Out's
frame for frame, settings included (check_soundingboard.py), but each box answers the chip's requests at its own speed
(a PC's 8086 against the Speak-Out's V40), so the sound is the same frames at slightly other moments -- not the same
samples.  Here: each sentence sounds (rms) and lasts within 5 % of the Speak-Out voice's.

    python tools/check_sb_voice.py [library]     (default build/win/x64/ssi263speech.dll)

Control (SB_VOICE_BREAK=1): the Sounding Board's folder is taken as missing SB.COM -- the voice must then be
unavailable and not made, and the sound checks fail.
"""
import ctypes
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FW = os.path.join(ROOT, "firmware")
TEXTS = ["Hello, this is the Sounding Board.", "The quick brown fox jumps over the lazy dog, 1234 times."]
BREAK = os.environ.get("SB_VOICE_BREAK") == "1"


def load(path):
    lib = ctypes.CDLL(path)
    lib.ssv_find.argtypes = [ctypes.c_char_p]
    lib.ssv_available.argtypes = [ctypes.c_int, ctypes.c_char_p]
    lib.ssv_create.restype = ctypes.c_void_p
    lib.ssv_create.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.ssv_speak.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.ssv_render.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_short)),
                               ctypes.POINTER(ctypes.c_int)]
    lib.ssv_destroy.argtypes = [ctypes.c_void_p]
    return lib


def speak(lib, v, text):
    pcm, done, out = ctypes.POINTER(ctypes.c_short)(), ctypes.c_int(0), []
    lib.ssv_speak(v, None, text.encode("utf-8"), 0)
    for _ in range(20000):
        n = lib.ssv_render(v, ctypes.byref(pcm), ctypes.byref(done))
        if n > 0:
            out.extend(pcm[:n])
        if done.value or n < 0:
            break
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "build", "win", "x64", "ssi263speech.dll")
    if not all(os.path.isfile(os.path.join(FW, "gw-micro-sounding-board", f)) for f in ("SBLOAD.COM", "SB.COM")):
        print("skip  the Sounding Board voice: its drivers are not in firmware/gw-micro-sounding-board")
        return 0
    lib = load(path)
    failures = 0

    def ok(cond, name, detail):
        nonlocal failures
        print("%-5s %-44s %s" % ("ok" if cond else "FAIL", name, detail))
        failures += not cond

    fw = FW
    tmp = None
    if BREAK:                                    # the control: a firmware folder whose Sounding Board lacks SB.COM
        tmp = tempfile.mkdtemp(prefix="sb_voice_")
        os.makedirs(os.path.join(tmp, "gw-micro-sounding-board"))
        shutil.copy(os.path.join(FW, "gw-micro-sounding-board", "SBLOAD.COM"), os.path.join(tmp, "gw-micro-sounding-board"))
        shutil.copytree(os.path.join(FW, "gw-micro-speakout"), os.path.join(tmp, "gw-micro-speakout"))
        fw = tmp
    try:
        i = lib.ssv_find(b"speakout:soundingboard")
        so = lib.ssv_find(b"speakout:speakout")
        ok(i >= 0, "listed: speakout:soundingboard", "index %d" % i)
        avail = i >= 0 and lib.ssv_available(i, fw.encode())
        ok(avail, "available with SBLOAD.COM and SB.COM", "yes" if avail else "no")
        err = ctypes.create_string_buffer(300)
        v = lib.ssv_create(i, fw.encode(), None, err, 300) if i >= 0 else None
        ok(bool(v), "the voice made", err.value.decode() or "made")
        w = lib.ssv_create(so, fw.encode(), None, err, 300)
        for text in TEXTS:
            a = speak(lib, v, text) if v else []
            b = speak(lib, w, text) if w else []
            rms = (sum(x * x for x in a) / len(a)) ** 0.5 if a else 0.0
            near = bool(a) and bool(b) and abs(len(a) - len(b)) <= 0.05 * len(b)
            ok(rms > 500 and near, "speaks: %s" % text[:28], "%d samples, rms %.0f (the Speak-Out voice: %d samples)" % (
                len(a), rms, len(b)))
        for x in (v, w):
            if x:
                lib.ssv_destroy(x)
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    print("sb voice: %s" % ("all passed" if not failures else "%d FAILED" % failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

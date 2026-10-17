"""The voice on every Braille Lite release that only the emulator had (bl_languages.txt rows with no shipped voice):
for each whose firmware is in the firmware folder, its state made by its own recipe, then the voice booted on it
(blv_create: the release's own boot keys and echo, bl_voice.c) with the release's text encoding, and a sentence said.

  speaks = yes   the sentence heard (0.8 s of speech or more) and the voice done within 3.6 s of audio -- a unit that
                 never echoes ^F is judged by the chip (no_echo), else its done would take the ~4.5-s timeout path
  speaks = no    silent (Japanese: not yet understood; Chinese: the unit has no speech)

    python test_release_voices.py [--firmware DIR] [--lib PATH] [--chip PATH]

Controls (SSI263_RELEASE_VOICES_BREAK, bl_voice.h blv_voice_break): fast boots every firmware with the shipped
voices' fast keys -- the slower firmwares (Czech, Russian, Greek, Hebrew, Arabic, French) must fall silent; echo
ignores the release's echo -- the units that never echo must take the timeout path.  The shipped voices' releases
are left to their own byte-for-byte tests.
"""
import argparse
import ctypes
import os
import struct
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
import gen_languages  # noqa: E402
import test_releases  # noqa: E402

WINDOWS = sys.platform == "win32"
BREAK = {"": 0, "fast": 1, "echo": 2}[os.environ.get("SSI263_RELEASE_VOICES_BREAK", "")]
RATE = 22050
TEXT = b"Hello. One two three."
TEXTS = {"7bit": 0, "850": 1, "852": 2, "857": 3, "860": 4, "866": 5, "hun": 6, "852sk": 7, "852pl": 8, "852hr": 9, "850fr": 10, "850dano": 11, "850sv": 12, "850es": 13, "850it": 14, "857tr": 15, "860pt": 16, "866ru": 17, "864ar": 18, "-": 0}
SHAPE = {"english": 0, "slow": 1}
SHIPPED = {"english", "spanish", "german", "italian", "slovak"}   # the shipped voices: their own tests
PROGRESS = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_double)
lib = None


def load(lib_path, chip_path):
    global lib
    test_releases.load(lib_path, chip_path)
    lib = test_releases.lib
    lib.blv_create.restype = ctypes.c_void_p
    lib.blv_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_double, ctypes.c_int,
                               ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.blv_speak.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.blv_render.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_short)),
                               ctypes.POINTER(ctypes.c_int)]
    lib.blv_destroy.argtypes = [ctypes.c_void_p]
    ctypes.c_int.in_dll(lib, "blv_voice_break").value = BREAK


def speak(job):
    """In a worker: (row index, firmware, state path, text encoding) -> (row, error or None, done s, speech s, rms)."""
    k, fw, st, enc = job
    err = ctypes.create_string_buffer(300)
    if not lib.blv_make_release_state(fw.encode(), k, st.encode(), PROGRESS(0), None, err, 300):
        return k, "state: " + err.value.decode(errors="replace"), 0, 0, 0
    v = lib.blv_create(fw.encode(), st.encode(), enc, float(RATE), 1, 0, err, 300)
    if not v:
        return k, "voice: " + err.value.decode(errors="replace"), 0, 0, 0
    lib.blv_speak(v, TEXT)
    pcm, done, y, total = ctypes.POINTER(ctypes.c_short)(), ctypes.c_int(0), [], 0
    while not done.value and total < 12 * RATE:
        n = lib.blv_render(v, ctypes.byref(pcm), ctypes.byref(done))
        if n:
            y.extend(pcm[i] / 32768 for i in range(n))
            total += n
    lib.blv_destroy(v)
    os.remove(st)
    y = y or [0.0]
    sq = [s * s for s in y]
    return k, None, total / RATE if done.value else 99.0, speech_span(sq), (sum(sq) / len(sq)) ** 0.5


def speech_span(sq):
    """Seconds from the first to the last sample whose 10 ms RMS (a centred moving mean of the squares, numpy's
    convolve "same") is over 0.01 -- in plain Python, so the test needs no numpy (the Pi's Debian has none)."""
    w = RATE // 100
    n = len(sq)
    if n <= w:
        loud = [i for i, s in enumerate(sq) if s ** 0.5 > 0.01]
    else:
        pre = [0.0]
        for s in sq:
            pre.append(pre[-1] + s)
        h = (w - 1) // 2               # convolve "same": output i is the full output's i + (w-1)//2
        loud = [i for i in range(n)
                if (pre[min(n, i + h + 1)] - pre[max(0, i + h + 1 - w)]) / w > 0.0001]
    return (loud[-1] - loud[0]) / RATE if loud else 0.0


def main():
    arch = "x64" if struct.calcsize("P") == 8 else "x86"
    ap = argparse.ArgumentParser()
    ap.add_argument("--firmware", default=os.environ.get("SSI263_FIRMWARE") or os.path.join(REPO, "firmware", "blazie"))
    ap.add_argument("--lib", default=os.path.join(REPO, "nvda", "dist", "blazie-lib", arch, "bl.dll") if WINDOWS
                    else os.path.join(REPO, "build", "linux", "libssi263speech.so"))
    ap.add_argument("--chip", default=os.path.join(REPO, "src", "ssi263", "_bin", arch, "ssi263.dll") if WINDOWS
                    else None)
    a = ap.parse_args()
    table, problems = gen_languages.rows()
    if problems:
        sys.exit("bl_languages.txt: " + "; ".join(problems))
    found = test_releases.find_images(a.firmware, table)
    tmp = tempfile.mkdtemp(prefix="ssi263-release-voices-")
    jobs = [(k, found[k], os.path.join(tmp, "%s.state" % table[k]["id"]), TEXTS[table[k]["text"]])
            for k in sorted(found) if table[k]["voice"] not in SHIPPED and table[k]["model"] == "bl"]
    for k, r in enumerate(table):
        if r["voice"] not in SHIPPED and r["model"] == "bl" and k not in found:
            print("skip %s: its firmware is not in the firmware folder" % r["id"])
    bad = 0
    with ProcessPoolExecutor(max_workers=max(1, min(len(jobs), (os.cpu_count() or 2) // 2)), initializer=load,
                             initargs=(a.lib, a.chip)) as ex:
        for k, error, done_s, speech_s, rms in ex.map(speak, jobs):
            r = table[k]
            if error:
                ok, what = False, error
            elif r["speaks"] == "yes":
                ok = speech_s >= 0.8 and done_s <= 3.6
                what = "speaks: %.1f s of speech, done at %.1f s (%s boot, echo %s)" % (
                    speech_s, done_s, r["boot"], r["echo"]) if done_s < 99 else "speaks: NO DONE in 12 s"
            else:
                ok = rms < 0.002
                what = "silent, as listed (rms %.4f)" % rms
            print("%-4s %s: %s" % ("ok" if ok else "FAIL", r["id"], what))
            bad += not ok
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    print("release voices: every case as expected" if not bad else "release voices: %d FAILED" % bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

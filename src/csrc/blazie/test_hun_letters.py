"""The Hungarian Braille Lite voice says its accented letters (bl_cphun.h): the voice booted on BL2HUN.BNS with its
release's text encoding, each of the nine accented vowels spoken in "b_t", lower and upper case, and the phonemes the
emulated unit loads checked against what the unit's own rules say for that byte (read from the emulator, bl_cphun.h).

    python test_hun_letters.py [--firmware DIR] [--lib PATH] [--chip PATH]

  bytes   blv_say_bytes: o double acute in both cases goes out as A7h, the others as their bytes
  vowel   each letter's word: the expected phoneme in the unit's loads (a long vowel three times, as the unit does)

Control (SSI263_HUN_BREAK=1): the voice and the bytes use the old encoding (plain letters, as before this table), so
every accented vowel turns into its base letter's sound -- this test must fail.
"""
import argparse
import ctypes
import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
import gen_languages  # noqa: E402
import test_releases  # noqa: E402

WINDOWS = sys.platform == "win32"
BREAK = os.environ.get("SSI263_HUN_BREAK") == "1"
RATE = 22050
CPHUN = 6                                    # bl_voice.h BLV_CPHUN
NAMES = ("PA E E1 Y Y1 AY IE I A AI EH EH1 AE AE1 AH AH1 AW O OU OO IU IU1 U U1 UH UH1 UH2 UH3 ER R R1 R2 L L1 LF W B "
         "D KV P T K HV HVC HF HFC HN Z S J SCH V F THV TH M N NG :A :OH :U :UH E2 LB").split()
# letter: (its byte, the phoneme the unit says for it, how many times) -- the emulated unit's own answers
VOWELS = {"á": (0xA0, "AE1", 3), "é": (0x82, "A", 3), "í": (0xA1, "E", 3), "ó": (0xA2, "OU", 3),
          "ö": (0x94, "E2", 1), "ő": (0xA7, "IU1", 3), "ú": (0xA3, "U1", 3), "ü": (0x81, ":U", 1),
          "ű": (0x96, ":U", 3),
          "Á": (0x8F, "AE1", 3), "É": (0x90, "A", 3), "Í": (0x8C, "E", 3), "Ó": (0x95, "OU", 3),
          "Ö": (0x99, "E2", 1), "Ő": (0xA7, "IU1", 3), "Ú": (0x97, "U1", 3), "Ü": (0x9A, ":U", 1),
          "Ű": (0x98, ":U", 3)}


class W(ctypes.Structure):
    _fields_ = [("t", ctypes.c_double), ("reg", ctypes.c_int), ("val", ctypes.c_int)]


def load(lib_path, chip_path):
    test_releases.load(lib_path, chip_path)
    lib = test_releases.lib
    lib.blv_create.restype = ctypes.c_void_p
    lib.blv_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_double, ctypes.c_int,
                               ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.blv_host.restype = ctypes.c_void_p
    lib.blv_host.argtypes = [ctypes.c_void_p]
    lib.blv_speak.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.blv_render.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_short)),
                               ctypes.POINTER(ctypes.c_int)]
    lib.blv_destroy.argtypes = [ctypes.c_void_p]
    lib.blv_say_bytes.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.bh_set_int.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.bh_writes.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(W))]
    lib.bh_clear_writes.argtypes = [ctypes.c_void_p]
    return lib


def phonemes(lib, v, h, text):
    """The phoneme codes the unit loads saying text, a run of pauses as one PA."""
    lib.bh_clear_writes(h)
    lib.bh_set_int(h, b"log_writes", 1)
    lib.blv_speak(v, text.encode("utf-8"))
    pcm, done, total = ctypes.POINTER(ctypes.c_short)(), ctypes.c_int(0), 0
    while not done.value and total < 8 * RATE:
        total += lib.blv_render(v, ctypes.byref(pcm), ctypes.byref(done))
    wp = ctypes.POINTER(W)()
    n = lib.bh_writes(h, ctypes.byref(wp))
    ph = [NAMES[wp[i].val & 0x3F] for i in range(n) if wp[i].reg == 0]
    lib.bh_set_int(h, b"log_writes", 0)
    return [p for i, p in enumerate(ph) if p != "PA" or (i and ph[i - 1] != "PA")]


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
    k = next(i for i, r in enumerate(table) if r["id"] == "bl2_hu_1999_07")
    fw = test_releases.find_images(a.firmware, table).get(k)
    if not fw:
        print("skip: BL2HUN.BNS is not in the firmware folder")
        return
    lib = load(a.lib, a.chip)
    enc = 0 if BREAK else test_releases.TEXT_ID[table[k]["text"]]
    bad = 0

    def report(ok, what):
        nonlocal bad
        print("%-4s %s" % ("ok" if ok else "FAIL", what))
        bad += not ok

    report(enc == CPHUN, "row     bl2_hu_1999_07's text encoding is hun (BLV_CPHUN %d): %d" % (CPHUN, enc))
    buf = ctypes.create_string_buffer(256)
    for letter, (byte, _, _) in VOWELS.items():
        n = lib.blv_say_bytes(("b%st" % letter).encode("utf-8"), enc, 0, buf, 256)
        got = buf.raw[:n].split(b"\r")[0]
        report(got == b"b" + bytes([byte]) + b"t", "bytes   U+%04X -> %r (want b\\x%02x t)" % (ord(letter), got, byte))

    st = os.path.join(tempfile.mkdtemp(prefix="ssi263-hun-"), "hu.state")
    err = ctypes.create_string_buffer(300)
    if not lib.blv_make_release_state(fw.encode(), k, st.encode(), test_releases.PROGRESS(0), None, err, 300):
        sys.exit("state: " + err.value.decode(errors="replace"))
    v = lib.blv_create(fw.encode(), st.encode(), enc, float(RATE), 1, 0, err, 300)
    if not v:
        sys.exit("voice: " + err.value.decode(errors="replace"))
    h = lib.blv_host(v)
    for letter, (_, ph, times) in VOWELS.items():
        got = phonemes(lib, v, h, "b%st" % letter)
        n = got.count(ph)
        report(got[:2] == ["B", "PA"] and n == times,
               "vowel   U+%04X in b_t: %s (want %s x%d)" % (ord(letter), " ".join(got), ph, times))
    lib.blv_destroy(v)
    os.remove(st)
    os.rmdir(os.path.dirname(st))
    print("hungarian letters: every check passed" if not bad else "hungarian letters: %d FAILED" % bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

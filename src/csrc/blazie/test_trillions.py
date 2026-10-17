"""The trillion guard (bl_numbers.c bl_trillions, blazie.py _trillions; bl_languages.txt's trillions column): a unit
whose own reader folds a trillion into billions gets a number of 13 digits or more a digit at a time, when the
voice's number processing is on.  Through the unified library (ssi263speech.dll, or libssi263speech.so):

  text    bl_trillions on known cases: 13 digits and more a digit at a time, 12 as they are, groups of three after
          the same "," or "." one number, a decimal part left as it is, a "," that is no group not one
  unit    the Hungarian unit (a folding release) through bl_voice with bl_trillions: saying 1,001,000,000,000 it
          says its billion word (from its own 1,000,000,000) no more than once
  voice   voices.c, the front ends' path (Android, speech-dispatcher, SAPI): the Hungarian voice with number
          processing on says "1001000000000." sample for sample as with it off says "1 0 0 1 0 0 0 0 0 0 0 0 0." --
          and not as with it off says "1001000000000."; the Russian voice (it reads trillions) the same either way

    python test_trillions.py [--firmware DIR] [--lib PATH]

The Hungarian and Russian images are looked for in the firmware folder and one folder below (bl2000/); a case whose
firmware is not there is skipped, and said so.  Control (SSI263_TRILLIONS_BREAK=1, bl_trillions_break): every number
left as it is, so the text cases past twelve digits, the unit (it folds) and the Hungarian voice fail.
"""
import argparse
import ctypes
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
import gen_languages  # noqa: E402
import test_releases  # noqa: E402
import test_unit_letters as L  # noqa: E402

BREAK = os.environ.get("SSI263_TRILLIONS_BREAK") == "1"
WINDOWS = sys.platform == "win32"
TEXT = [("1001000000000", "1 0 0 1 0 0 0 0 0 0 0 0 0"), ("999999999999", "999999999999"),
        ("1,234,567,890,123", "1 2 3 4 5 6 7 8 9 0 1 2 3"), ("1.234.567.890.123,5", "1 2 3 4 5 6 7 8 9 0 1 2 3,5"),
        ("12345678901234.5 x", "1 2 3 4 5 6 7 8 9 0 1 2 3 4.5 x"), ("1234567890.123", "1234567890.123"),
        ("1,234,5678", "1,234,5678"), ("call 0012345678901", "call 0 0 1 2 3 4 5 6 7 8 9 0 1"),
        ("1,234.567.890.123", "1,234.567.890.123"), ("ő1234567890123ő", "ő1 2 3 4 5 6 7 8 9 0 1 2 3ő")]


class Settings(ctypes.Structure):
    _fields_ = [(n, ctypes.c_int) for n in ("rate", "pitch", "volume", "tone", "pack", "join", "inflection",
                                            "numbers", "run_ahead", "line_lift")]


def load(path):
    lib = ctypes.CDLL(path)
    lib.bl_trillions.restype = ctypes.c_void_p
    lib.bl_trillions.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.blv_set_numbers.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    lib.blv_make_release_state.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, test_releases.PROGRESS,
                                           ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    ctypes.c_int.in_dll(lib, "bl_trillions_break").value = 1 if BREAK else 0
    # the voice table (voices.c): in the Windows library; on Linux it is built into the speech-dispatcher module
    # (sd_ssi263) alone, so libssi263speech.so has none and the voice cases are skipped there (the unit's are not)
    lib.has_voices = hasattr(lib, "ssv_find")
    if not lib.has_voices:
        return lib
    lib.ssv_find.argtypes = [ctypes.c_char_p]
    lib.ssv_create.restype = ctypes.c_void_p
    lib.ssv_create.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.ssv_defaults.argtypes = [ctypes.c_int, ctypes.POINTER(Settings)]
    lib.ssv_speak.argtypes = [ctypes.c_void_p, ctypes.POINTER(Settings), ctypes.c_char_p, ctypes.c_int]
    lib.ssv_render.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_short)),
                               ctypes.POINTER(ctypes.c_int)]
    lib.ssv_destroy.argtypes = [ctypes.c_void_p]
    return lib


def trillions(lib, text):
    p = lib.bl_trillions(text.encode("utf-8"), 0)
    out = ctypes.string_at(p).decode("utf-8")
    ctypes.CDLL("msvcrt" if WINDOWS else None).free(ctypes.c_void_p(p))
    return out


def voice_pcm(lib, i, fwdir, numbers, text):
    """One utterance on a freshly booted voice (a unit that has spoken is not where a fresh one starts)."""
    err = ctypes.create_string_buffer(300)
    v = lib.ssv_create(i, fwdir.encode(), None, err, 300)
    if not v:
        return None
    s = Settings()
    lib.ssv_defaults(i, ctypes.byref(s))
    s.numbers = numbers
    lib.ssv_speak(v, ctypes.byref(s), text.encode("utf-8"), 0)
    pcm, done, out = ctypes.POINTER(ctypes.c_short)(), ctypes.c_int(0), bytearray()
    while not done.value and len(out) < 2 * 22050 * 40:
        n = lib.ssv_render(v, ctypes.byref(pcm), ctypes.byref(done))
        out += ctypes.string_at(pcm, 2 * n) if n > 0 else b""
    lib.ssv_destroy(v)
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--firmware", default=os.environ.get("SSI263_FIRMWARE") or os.path.join(REPO, "firmware", "blazie"))
    arch = "x64" if struct.calcsize("P") == 8 else "x86"
    ap.add_argument("--lib", default=os.path.join(REPO, "build", "win", arch, "ssi263speech.dll") if WINDOWS
                    else os.path.join(REPO, "build", "linux", "libssi263speech.so"))
    a = ap.parse_args()
    lib = load(a.lib)
    bad = 0

    def result(ok, what, detail):
        nonlocal bad
        print("%-4s %-8s %s" % ("ok" if ok else "FAIL", what, detail))
        bad += not ok

    for text, want in TEXT:
        got = trillions(lib, text)
        result(got == want, "text", "%a -> %a%s" % (text, got, "" if got == want else " (want %a)" % want))

    table, _ = gen_languages.rows()
    found = test_releases.find_images(a.firmware, table)
    rows = {table[k]["id"]: k for k in found}
    tmp = tempfile.mkdtemp(prefix="ssi263_trillions_")
    try:
        fw = os.path.join(tmp, "blazie", "bl2000")         # voices.c's layout of a release voice's files
        os.makedirs(fw)
        err = ctypes.create_string_buffer(300)
        have = {}
        for rid in ("bl2_hu_1999_07", "bl2_ru_1998_12"):
            if rid not in rows:
                print("skip %-8s %s: its firmware is not in %s" % ("voice", rid, a.firmware))
                continue
            k = rows[rid]
            shutil.copyfile(found[k], os.path.join(fw, table[k]["file"]))
            st = os.path.join(fw, rid + ".state")
            if not lib.blv_make_release_state(found[k].encode(), k, st.encode(), test_releases.PROGRESS(0), None,
                                              err, 300):
                result(False, "state", "%s: %s" % (rid, err.value.decode(errors="replace")))
                continue
            have[rid] = (k, st)

        if "bl2_hu_1999_07" in have:            # the unit's own words, through bl_voice and bl_trillions
            k, st = have["bl2_hu_1999_07"]
            L.worker_init(a.lib, None)
            ll = L._lib
            ll.blv_set_numbers.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            v = ll.blv_create(found[k].encode(), st.encode(), test_releases.TEXT_ID[table[k]["text"]], 22050.0, 1, 0,
                              err, 300)
            h = ll.blv_host(v)
            one = L.phonemes(ll, v, h, "1.").replace("PA", "").split()
            word = L.phonemes(ll, v, h, "1000000000.").replace("PA", "").split()[len(one):]
            ll.blv_set_numbers(v, ctypes.cast(lib.bl_trillions, ctypes.c_void_p))
            said = L.phonemes(ll, v, h, "1001000000000.").replace("PA", "").split()
            n = sum(1 for i in range(len(said) - len(word) + 1) if said[i:i + len(word)] == word) if word else 0
            result(word and n <= 1, "unit", "the Hungarian unit's billion word [%s] said %d time%s in "
                   "1,001,000,000,000 with the guard" % (" ".join(word), n, "" if n == 1 else "s"))
            ll.blv_destroy(v)

        if not lib.has_voices:
            print("skip voice    this library has no voice table (on Linux voices.c is the speech-dispatcher "
                  "module's alone)")
        for rid, folds in (("bl2_hu_1999_07", True), ("bl2_ru_1998_12", False)):
            if rid not in have or not lib.has_voices:
                continue
            i = lib.ssv_find(("blazie:" + table[have[rid][0]]["voice"]).encode())
            guarded = voice_pcm(lib, i, tmp, 1, "1001000000000.")
            digits = voice_pcm(lib, i, tmp, 0, "1 0 0 1 0 0 0 0 0 0 0 0 0.")
            own = voice_pcm(lib, i, tmp, 0, "1001000000000.")
            if guarded is None:
                result(False, "voice", "%s: the voice would not start" % rid)
                continue
            if folds:
                result(guarded == digits and guarded != own, "voice", "%s, number processing on: %s the digits one "
                       "by one, %s its own reading" % (rid, "as" if guarded == digits else "NOT as",
                                                         "not as" if guarded != own else "AS"))
            else:
                result(guarded == own, "voice", "%s (reads trillions), number processing on: %s its own reading"
                       % (rid, "as" if guarded == own else "NOT as"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("trillions: %s" % ("%d FAILED" % bad if bad else "all passed"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

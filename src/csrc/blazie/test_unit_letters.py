"""Each unit says its own accented letters through the voice: the voice booted on the release with its text encoding
(bl_languages.txt's text column, bl_voice.c), each letter of the language spoken in a short frame, lower and upper
case, and the phonemes the emulated unit loads compared with what the unit says for that letter's byte sent raw.
The expected strings were read from the emulator (every byte 80h-FFh sent in the same frame, 2026-10-15/16).

    python test_unit_letters.py [--firmware DIR] [--lib PATH] [--chip PATH]

  row     the release's text encoding is the one these letters need
  bytes   blv_say_bytes: each letter's byte (a folded letter goes out as the one the unit speaks: Hungarian o double
          acute as A7h, Slovak o circumflex as E2h -- their lower case bytes say nothing)
  letter  each letter in its frame: exactly the unit's own phonemes for that byte

A letter the unit says nothing for in either case goes out as its base letter, and must be said exactly as that.

Control (SSI263_LETTERS_BREAK=1): each voice sends what it did before these tables (plain letters, plain 852 or 850),
so the Hungarian vowels, the Czech and Scandinavian letters, the Slovak o circumflex and the capitals the Polish,
Croatian and French units skip fail.  This test must then fail.
"""
import argparse
import ctypes
import os
import struct
import sys
import tempfile
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
import gen_languages  # noqa: E402
import test_releases  # noqa: E402

WINDOWS = sys.platform == "win32"
BREAK = os.environ.get("SSI263_LETTERS_BREAK") == "1"
RATE = 22050
NAMES = ("PA E E1 Y Y1 AY IE I A AI EH EH1 AE AE1 AH AH1 AW O OU OO IU IU1 U U1 UH UH1 UH2 UH3 ER R R1 R2 L L1 LF W B "
         "D KV P T K HV HVC HF HFC HN Z S J SCH V F THV TH M N NG :A :OH :U :UH E2 LB").split()


def hu(ph, n):
    return " ".join(["B PA"] + ["%s PA" % ph] * n + ["T PA"])


# release: (its text encoding, the encoding before (the control), frame, {letter: (byte, the unit's phonemes)})
RELEASES = {
    "bl2_hu_1999_07": (6, 0, "b{}t", {
        "á": (0xA0, hu("AE1", 3)), "é": (0x82, hu("A", 3)), "í": (0xA1, hu("E", 3)),
        "ó": (0xA2, hu("OU", 3)), "ö": (0x94, hu("E2", 1)), "ő": (0xA7, hu("IU1", 3)),
        "ú": (0xA3, hu("U1", 3)), "ü": (0x81, hu(":U", 1)), "ű": (0x96, hu(":U", 3)),
        "Á": (0x8F, hu("AE1", 3)), "É": (0x90, hu("A", 3)), "Í": (0x8C, hu("E", 3)),
        "Ó": (0x95, hu("OU", 3)), "Ö": (0x99, hu("E2", 1)), "Ő": (0xA7, hu("IU1", 3)),
        "Ú": (0x97, hu("U1", 3)), "Ü": (0x9A, hu(":U", 1)), "Ű": (0x98, hu(":U", 3))}),
    "bns2_sk": (7, 2, "sa{}sa", {
        "á": (0xA0, "S PA UH3 PA UH3 PA UH3 PA S PA UH3 PA"),
        "Á": (0xB5, "S PA UH3 PA UH3 PA UH3 PA S PA UH3 PA"),
        "ä": (0x84, "S PA UH3 PA EH PA S PA UH3 PA"),
        "Ä": (0x8E, "S PA UH3 PA EH PA S PA UH3 PA"),
        "č": (0x9F, "S PA UH3 PA T PA SCH PA S PA UH3 PA"),
        "Č": (0xAC, "S PA UH3 PA T PA SCH PA S PA UH3 PA"),
        "ď": (0xD4, "S PA UH3 PA D PA NG PA S PA UH3 PA"),
        "Ď": (0xD2, "S PA UH3 PA D PA NG PA S PA UH3 PA"),
        "é": (0x82, "S PA UH3 PA EH1 PA EH1 PA S PA UH3 PA"),
        "É": (0x90, "S PA UH3 PA EH1 PA EH1 PA S PA UH3 PA"),
        "í": (0xA1, "S PA UH3 PA E PA E PA S PA UH3 PA"),
        "Í": (0xD6, "S PA UH3 PA E PA E PA S PA UH3 PA"),
        "ĺ": (0x92, "S PA UH3 PA L1 PA L1 PA S PA UH3 PA"),
        "Ĺ": (0x91, "S PA UH3 PA L1 PA L1 PA S PA UH3 PA"),
        "ľ": (0x96, "S PA UH3 PA L1 PA NG PA S PA UH3 PA"),
        "Ľ": (0x95, "S PA UH3 PA L1 PA NG PA S PA UH3 PA"),
        "ň": (0xE5, "S PA UH3 PA N PA NG PA S PA UH3 PA"),
        "Ň": (0xD5, "S PA UH3 PA N PA NG PA S PA UH3 PA"),
        "ó": (0xA2, "S PA UH3 PA O PA O PA S PA UH3 PA"),
        "Ó": (0xE0, "S PA UH3 PA O PA O PA S PA UH3 PA"),
        "ô": (0xE2, "S PA UH3 PA W PA O PA S PA UH3 PA"),
        "Ô": (0xE2, "S PA UH3 PA W PA O PA S PA UH3 PA"),
        "ŕ": (0xEA, "S PA UH3 PA R1 PA R1 PA R1 PA R1 PA S PA UH3 PA"),
        "Ŕ": (0xE8, "S PA UH3 PA R1 PA R1 PA R1 PA R1 PA S PA UH3 PA"),
        "š": (0xE7, "S PA UH3 PA SCH PA S PA UH3 PA"),
        "Š": (0xE6, "S PA UH3 PA SCH PA S PA UH3 PA"),
        "ť": (0x9C, "S PA UH3 PA T PA NG PA S PA UH3 PA"),
        "Ť": (0x9B, "S PA UH3 PA T PA NG PA S PA UH3 PA"),
        "ú": (0xA3, "S PA UH3 PA U PA U PA S PA UH3 PA"),
        "Ú": (0xE9, "S PA UH3 PA U PA U PA S PA UH3 PA"),
        "ý": (0xEC, "S PA UH3 PA E PA E PA S PA UH3 PA"),
        "Ý": (0xED, "S PA UH3 PA E PA E PA S PA UH3 PA"),
        "ž": (0xA7, "S PA UH3 PA J PA S PA UH3 PA"),
        "Ž": (0xA6, "S PA UH3 PA J PA S PA UH3 PA")}),
    "bl2_cs_1999_07": (7, 0, "b{}t", {
        "á": (0xA0, "B PA UH3 PA UH3 PA T PA"), "Á": (0xB5, "B PA UH3 PA UH3 PA T PA"),
        "č": (0x9F, "B PA T PA SCH PA T PA"), "Č": (0xAC, "B PA T PA SCH PA T PA"),
        "ď": (0xD4, "B PA D PA NG PA T PA"), "Ď": (0xD2, "B PA D PA NG PA T PA"),
        "é": (0x82, "B PA EH1 PA EH1 PA T PA"), "É": (0x90, "B PA EH1 PA EH1 PA T PA"),
        "ě": (0xD8, "B PA Y1 PA EH1 PA T PA"), "Ě": (0xB7, "B PA Y1 PA EH1 PA T PA"),
        "í": (0xA1, "B PA E PA E PA T PA"), "Í": (0xD6, "B PA E PA E PA T PA"),
        "ň": (0xE5, "B PA N PA NG PA T PA"), "Ň": (0xD5, "B PA N PA NG PA T PA"),
        "ó": (0xA2, "B PA O PA O PA T PA"), "Ó": (0xE0, "B PA O PA O PA T PA"),
        "ř": (0xFD, "B PA R2 PA J PA T PA"), "Ř": (0xFC, "B PA R2 PA J PA T PA"),
        "š": (0xE7, "B PA SCH PA T PA"), "Š": (0xE6, "B PA SCH PA T PA"),
        "ť": (0x9C, "B PA T PA NG PA T PA"), "Ť": (0x9B, "B PA T PA NG PA T PA"),
        "ú": (0xA3, "B PA U PA U PA T PA"), "Ú": (0xE9, "B PA U PA U PA T PA"),
        "ů": (0x85, "B PA U PA U PA T PA"), "Ů": (0xDE, "B PA U PA U PA T PA"),
        "ý": (0xEC, "B PA E PA E PA T PA"), "Ý": (0xED, "B PA E PA E PA T PA"),
        "ž": (0xA7, "B PA J PA T PA"), "Ž": (0xA6, "B PA J PA T PA")}),
    # (None: the unit says nothing for the letter in either case, so its base letter goes out and is said as that)
    "bl2_pl_1998_12": (8, 2, "sa{}sa", {
        "ą": (0xA5, "S PA AH1 PA O PA OU PA HN PA S PA AH1 PA"),
        "Ą": (0xA4, "S PA AH1 PA O PA OU PA HN PA S PA AH1 PA"),
        "ć": (0x86, "S PA AH1 PA T PA SCH PA Y PA S PA AH1 PA"),
        "Ć": (0x8F, "S PA AH1 PA T PA SCH PA Y PA S PA AH1 PA"),
        "ę": (0xA9, "S PA AH1 PA EH1 PA U PA N PA S PA AH1 PA"),
        "Ę": (0xA8, "S PA AH1 PA EH1 PA U PA N PA S PA AH1 PA"),
        "ł": (0x88, "S PA AH1 PA U PA S PA AH1 PA"),
        "Ł": (0x9D, "S PA AH1 PA U PA S PA AH1 PA"),
        "ń": (0xE4, "S PA AH1 PA N PA NG PA Y PA S PA AH1 PA"),
        "Ń": (0xE3, "S PA AH1 PA N PA NG PA Y PA S PA AH1 PA"),
        "ó": (0xA2, "S PA AH1 PA U PA U PA S PA AH1 PA"),
        "Ó": (0xE0, "S PA AH1 PA U PA U PA S PA AH1 PA"),
        "ś": (0x98, "S PA AH1 PA SCH PA S PA AH1 PA"),
        "Ś": (0x97, "S PA AH1 PA SCH PA S PA AH1 PA"),
        "ź": (0xAB, "S PA AH1 PA J PA SCH PA Y PA S PA AH1 PA"),
        "Ź": (0x8D, "S PA AH1 PA J PA SCH PA Y PA S PA AH1 PA"),
        "ż": (0xBE, "S PA AH1 PA J PA S PA AH1 PA"),
        "Ż": (0xBE, "S PA AH1 PA J PA S PA AH1 PA"),
        "ô": (None, None), "Ô": (None, None)}),
    "bl2_hr_1999_07": (9, 2, "sa{}sa", {
        "č": (0x9F, "S PA AH1 PA T PA SCH PA S PA AH1 PA"),
        "Č": (0xAC, "S PA AH1 PA T PA SCH PA S PA AH1 PA"),
        "ć": (0x86, "S PA AH1 PA T PA Y1 PA S PA AH1 PA"),
        "Ć": (0x86, "S PA AH1 PA T PA Y1 PA S PA AH1 PA"),
        "đ": (0xD0, "S PA AH1 PA D PA J PA J PA S PA AH1 PA"),
        "Đ": (0xD0, "S PA AH1 PA D PA J PA J PA S PA AH1 PA"),
        "š": (0xE7, "S PA AH1 PA SCH PA S PA AH1 PA"),
        "Š": (0xE6, "S PA AH1 PA SCH PA S PA AH1 PA"),
        "ž": (0xA7, "S PA AH1 PA J PA S PA AH1 PA"),
        "Ž": (0xA6, "S PA AH1 PA J PA S PA AH1 PA"),
        "ô": (None, None), "Ô": (None, None)}),
    "bl2_fr_fre_1999_07": (10, 1, "sa{}sa", {
        "à": (0x85, "S PA AH1 PA AH1 PA Z PA AH1 PA"), "À": (0x85, "S PA AH1 PA AH1 PA Z PA AH1 PA"),
        "â": (0x83, "S PA AH1 PA AH1 PA Z PA AH1 PA"), "Â": (0x83, "S PA AH1 PA AH1 PA Z PA AH1 PA"),
        "æ": (0x91, "S PA AH1 PA OU PA AE PA S PA AH1 PA"),
        "Æ": (0x92, "S PA AH1 PA OU PA AE PA S PA AH1 PA"),
        "ç": (0x87, "S PA AH1 PA S PA S PA AH1 PA"), "Ç": (0x87, "S PA AH1 PA S PA S PA AH1 PA"),
        "é": (0x82, "S PA AH1 PA A PA Z PA AH1 PA"), "É": (0x90, "S PA AH1 PA AY PA Z PA AH1 PA"),
        "è": (0x8A, "S PA AH1 PA AY PA Z PA AH1 PA"), "È": (0x8A, "S PA AH1 PA AY PA Z PA AH1 PA"),
        "ê": (0x88, "S PA AH1 PA AE PA Z PA AH1 PA"), "Ê": (0x88, "S PA AH1 PA AE PA Z PA AH1 PA"),
        "ë": (0x89, "S PA AH1 PA AE PA Z PA AH1 PA"), "Ë": (0x89, "S PA AH1 PA AE PA Z PA AH1 PA"),
        "î": (0x8C, "S PA AE PA Z PA AH1 PA"), "Î": (0x8C, "S PA AE PA Z PA AH1 PA"),
        "ï": (0x8B, "S PA AH1 PA IE PA Z PA AH1 PA"), "Ï": (0x8B, "S PA AH1 PA IE PA Z PA AH1 PA"),
        "ù": (0x97, "S PA AH1 PA U1 PA Z PA AH1 PA"), "Ù": (0x97, "S PA AH1 PA U1 PA Z PA AH1 PA"),
        "û": (0x96, "S PA AH1 PA :UH PA Z PA AH1 PA"), "Û": (0x96, "S PA AH1 PA :UH PA Z PA AH1 PA"),
        "ô": (None, None), "Ô": (None, None), "ü": (None, None), "Ü": (None, None),
        "ÿ": (None, None)}),
    "bl2_da_1999_11": (11, 0, "sa{}sa", {
        "æ": (0x91, "S PA AE PA EH PA S PA AE PA"), "Æ": (0x92, "S PA AE PA EH PA S PA AE PA"),
        "ø": (0x9B, "S PA AE PA ER PA S PA AE PA"), "Ø": (0x9D, "S PA AE PA ER PA S PA AE PA"),
        "å": (0x86, "S PA AE PA AH PA S PA AE PA"), "Å": (0x8F, "S PA AE PA AH PA S PA AE PA"),
        "é": (None, None), "É": (None, None), "ü": (None, None), "Ü": (None, None)}),
    "bl2_no_1999_07": (11, 0, "sa{}sa", {
        "æ": (0x91, "S PA AE PA EH PA S PA AE PA"), "Æ": (0x92, "S PA AE PA EH PA S PA AE PA"),
        "ø": (0x9B, "S PA AE PA ER PA S PA AE PA"), "Ø": (0x9D, "S PA AE PA ER PA S PA AE PA"),
        "å": (0x86, "S PA AE PA AH PA S PA AE PA"), "Å": (0x8F, "S PA AE PA AH PA S PA AE PA"),
        "é": (None, None), "É": (None, None), "ü": (None, None), "Ü": (None, None),
        "ô": (None, None), "Ô": (None, None)}),
    "bl2_sv_1999_07": (12, 0, "sa{}sa", {
        "å": (0x86, "S PA AE PA AH PA S PA AE PA"), "Å": (0x8F, "S PA AE PA AH PA S PA AE PA"),
        "ä": (0x84, "S PA AE PA EH PA S PA AE PA"), "Ä": (0x8E, "S PA AE PA EH PA S PA AE PA"),
        "ö": (0x94, "S PA AE PA :OH PA S PA AE PA"), "Ö": (0x99, "S PA AE PA :OH PA S PA AE PA"),
        "ü": (0x81, "S PA AE PA UH PA S PA AE PA"), "Ü": (0x9A, "S PA AE PA UH PA S PA AE PA"),
        "é": (0x90, "S PA AE PA EH PA S PA AE PA"), "É": (0x90, "S PA AE PA EH PA S PA AE PA")}),
}


def base(letter):
    """The letter without its accent: what translit.h sends for a letter the unit has no byte for."""
    return unicodedata.normalize("NFD", letter)[0]


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
    return " ".join(p for i, p in enumerate(ph) if p != "PA" or (i and ph[i - 1] != "PA"))


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
    lib = load(a.lib, a.chip)
    bad = 0

    def report(ok, what):
        nonlocal bad
        print("%-4s %s" % ("ok" if ok else "FAIL", what))
        bad += not ok

    tmp = tempfile.mkdtemp(prefix="ssi263-letters-")
    buf = ctypes.create_string_buffer(256)
    for rid, (want_text, before, frame, letters) in RELEASES.items():
        k = next(i for i, r in enumerate(table) if r["id"] == rid)
        text = test_releases.TEXT_ID[table[k]["text"]]
        report(text == want_text, "row     %s's text encoding is %d: %d" % (rid, want_text, text))
        enc = before if BREAK else text
        for letter, (byte, _) in letters.items():
            n = lib.blv_say_bytes(frame.format(letter).encode("utf-8"), enc, 0, buf, 256)
            got = buf.raw[:n].split(b"\r")[0]
            want = frame.format("\x00").encode().replace(b"\x00", base(letter).encode() if byte is None
                                                         else bytes([byte]))
            report(got == want, "bytes   %s U+%04X -> %r (want %r)" % (rid, ord(letter), got, want))
        if k not in found:
            print("skip %s: its firmware is not in the firmware folder" % rid)
            continue
        st = os.path.join(tmp, "%s.state" % rid)
        err = ctypes.create_string_buffer(300)
        if not lib.blv_make_release_state(found[k].encode(), k, st.encode(), test_releases.PROGRESS(0), None, err, 300):
            sys.exit("state: " + err.value.decode(errors="replace"))
        v = lib.blv_create(found[k].encode(), st.encode(), enc, float(RATE), 1, 0, err, 300)
        if not v:
            sys.exit("voice: " + err.value.decode(errors="replace"))
        h = lib.blv_host(v)
        for letter, (_, want) in letters.items():
            if want is None:                         # said as its base letter (and so not skipped)
                want = phonemes(lib, v, h, frame.format(base(letter)))
            got = phonemes(lib, v, h, frame.format(letter))
            report(got == want, "letter  %s U+%04X: %s%s" % (rid, ord(letter), got, "" if got == want else
                                                              " (want %s)" % want))
        lib.blv_destroy(v)
        os.remove(st)
    os.rmdir(tmp)
    print("unit letters: every check passed" if not bad else "unit letters: %d FAILED" % bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

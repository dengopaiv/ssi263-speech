"""The release table through the library (bl_languages.txt -> bl_languages_table.h -> bl_firmware.c's blv_release_*):
every row as the library reports it, and for every row whose firmware is in the firmware folder, blv_release_of
finding it and blv_make_release_state making its listed state, byte for byte (its recipe's shape and answer are the
row's).  The states are made in parallel, one process each.

    python test_releases.py [--firmware DIR] [--lib PATH] [--chip PATH]

--firmware (default $SSI263_FIRMWARE, else firmware/blazie) is searched with its subfolders for each row's image; a
row whose firmware is not there is skipped, and said so.  A release with no voice (the emulator's only), imported
through the voices' path (blv_import_firmware), must be refused as BLV_FW_NO_VOICE and leave no file: no language is
offered without its firmware AND its voice.  Controls (SSI263_RELEASES_TEST_BREAK): 1 answers every setup with n
instead of the row's letter (blv_make_state_yes), so every state made must differ from its row's; voice hands the
no-voice releases out as English (blv_firmware_break 2), so the no-voice case must fail; unit imports for a unit
through the voices' path (blv_import_firmware for blv_import_release), so the unit case must fail.

Every release found is imported for a unit too (blv_import_release, an emulator's import: Apple's unit tab): each
must come back as its own row, written as a .BNS that blv_release_of finds as that row -- the no-voice releases kept.
"""
import argparse
import ctypes
import hashlib
import os
import struct
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "src", "platforms", "android", "test"))
import gen_languages  # noqa: E402

WINDOWS = sys.platform == "win32"
BREAK_MODE = os.environ.get("SSI263_RELEASES_TEST_BREAK", "")
BREAK = BREAK_MODE not in ("", "voice", "unit")   # the states control
BREAK_VOICE = BREAK_MODE == "voice"               # the no-voice control (blv_firmware_break 2)
BREAK_UNIT = BREAK_MODE == "unit"                 # the unit control (the voices' import for a unit's)
FILE_ROM_OFFSET = 0x3000
PROGRESS = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_double)
VOICE = {"english": 0, "spanish": 1, "german": 2, "italian": 3, "slovak": 4, "-": -1}
MODEL = {"bl": 0, "bns": 1, "bns640": 2}
SHAPE = {"english": 0, "slow": 1}
TRILLIONS = {"-": 0, "fold": 1, "reads": 2, "digits": 3}   # bl_firmware.h BLV_TRILLIONS_*
TEXT_ID = {"7bit": 0, "850": 1, "852": 2, "857": 3, "860": 4, "866": 5, "hun": 6, "852sk": 7, "852pl": 8, "852hr": 9, "850fr": 10, "850dano": 11, "850sv": 12, "850es": 13, "850it": 14, "857tr": 15, "860pt": 16, "866ru": 17, "864ar": 18, "-": 0}   # bl_voice.h BLV_*
N_CHORD = 0x1D                                   # n in computer braille
NO_VOICE = -8                                    # bl_firmware.h BLV_FW_NO_VOICE

lib = None


def load(lib_path, chip_path):
    global lib
    import test_android_native as TAN
    lib = TAN.load_reference(lib_path, chip_path)
    for name in ("blv_firmware_label", "blv_release_id", "blv_release_name", "blv_release_tag", "blv_release_file"):
        getattr(lib, name).restype = ctypes.c_char_p
        getattr(lib, name).argtypes = [ctypes.c_int]
    for name in ("blv_firmware_language", "blv_release_model", "blv_release_code_page", "blv_release_text",
                 "blv_release_slow_boot", "blv_release_echo", "blv_release_speaks", "blv_release_trillions"):
        getattr(lib, name).argtypes = [ctypes.c_int]
    lib.blv_release_of.argtypes = [ctypes.c_char_p]
    lib.blv_import_firmware.argtypes = [ctypes.c_char_p, ctypes.c_long, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    lib.blv_import_release.argtypes = lib.blv_import_firmware.argtypes
    ctypes.c_int.in_dll(lib, "blv_firmware_break").value = 2 if BREAK_VOICE else 0
    lib.blv_make_release_state.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, PROGRESS,
                                           ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    lib.blv_make_state_yes.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_ubyte, ctypes.c_char_p, PROGRESS,
                                       ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    return lib


def make(job):
    """In a worker: (release, shape, firmware, out) -> (release, ok, the state's sha256 or the error)."""
    release, shape, firmware, out = job
    err = ctypes.create_string_buffer(256)
    if BREAK:
        ok = lib.blv_make_state_yes(firmware.encode(), shape, N_CHORD, out.encode(), PROGRESS(0), None, err, 256)
    else:
        ok = lib.blv_make_release_state(firmware.encode(), release, out.encode(), PROGRESS(0), None, err, 256)
    if not ok:
        return release, False, err.value.decode(errors="replace")
    with open(out, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    os.remove(out)
    return release, True, digest


def find_images(folder, table):
    """{row index: a file in folder holding its image at 3000h}."""
    want = {(r["length"], r["image"]): k for k, r in enumerate(table)}
    lengths = sorted({r["length"] for r in table})
    found = {}
    for root, _, files in os.walk(folder):
        for name in sorted(files):
            if not name.upper().endswith(".BNS"):
                continue
            path = os.path.join(root, name)
            if os.path.getsize(path) > FILE_ROM_OFFSET + 0x40000:
                continue
            data = open(path, "rb").read()[FILE_ROM_OFFSET:]
            for n in lengths:
                k = want.get((n, hashlib.sha256(data[:n]).hexdigest()))
                if k is not None and k not in found:
                    found[k] = path
    return found


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
    load(a.lib, a.chip)
    bad = 0

    def result(ok, what, detail=""):
        nonlocal bad
        print("%-4s %s%s" % ("ok" if ok else "FAIL", what, (": " + detail) if detail else ""))
        bad += not ok

    if not BREAK:
        got = [(lib.blv_release_id(k), lib.blv_release_name(k), lib.blv_release_tag(k), lib.blv_firmware_label(k),
                lib.blv_firmware_language(k), lib.blv_release_model(k), lib.blv_release_code_page(k),
                lib.blv_release_file(k), lib.blv_release_text(k), lib.blv_release_slow_boot(k), lib.blv_release_echo(k),
                lib.blv_release_speaks(k), lib.blv_release_trillions(k))
               for k in range(lib.blv_firmware_count())]
        want = [(r["id"].encode(), r["name"].encode(), r["tag"].encode(), r["label"].encode(), VOICE.get(r["voice"], -1),
                 MODEL[r["model"]], int(r["cp"]) if r["cp"] != "-" else 0, r["file"].encode(), TEXT_ID[r["text"]],
                 int(r["boot"] == "slow"), int(r["echo"] == "yes"), int(r["speaks"] == "yes"),
                 TRILLIONS[r["trillions"]]) for r in table]
        result(got == want, "the library's list = bl_languages.txt (%d releases: id, name, language, label, voice, "
               "model, code page, file, text, boot, echo, speaks, trillions)" % len(want), "" if got == want else "first difference at row %d" %
               next(k for k in range(max(len(got), len(want))) if k >= len(got) or k >= len(want) or got[k] != want[k]))
        n = len(table)
        result(lib.blv_release_id(n) is None and lib.blv_release_name(n) is None and lib.blv_release_tag(-1) is None
               and lib.blv_release_model(n) == -1 and lib.blv_release_code_page(-1) == -1, "past the list: none")
    found = find_images(a.firmware, table)
    for k, r in enumerate(table):
        if k not in found:
            print("skip %s: its firmware is not in the firmware folder" % r["id"])
    if not BREAK:
        located = {k: lib.blv_release_of(p.encode()) for k, p in found.items()}
        wrong = [table[k]["id"] for k, got in located.items() if got != k]
        result(not wrong, "blv_release_of: each of %d .BNS files found as its own release" % len(found),
               ", ".join(wrong))
    tmp = tempfile.mkdtemp(prefix="ssi263-releases-test-")
    if not BREAK:
        # no voice without its firmware AND its voice: a no-voice release brought to a voice importer is refused
        mute = [k for k in sorted(found) if VOICE.get(table[k]["voice"], -1) == -1]   # no shipped voice (yet: the phones)
        handed = []
        out = os.path.join(tmp, "imported.BNS")
        for k in mute:
            data = open(found[k], "rb").read()
            msg = ctypes.create_string_buffer(256)
            r = lib.blv_import_firmware(data, len(data), out.encode(), msg, 256)
            if r != NO_VOICE or os.path.exists(out):
                handed.append("%s -> %d" % (table[k]["id"], r))
            if os.path.exists(out):
                os.remove(out)
        if mute:
            result(not handed, "no voice offered for the %d releases without one (the emulator's only): each import "
                   "refused as not yet a voice, no file left" % len(mute), ", ".join(handed[:4]))
        # for a unit, every release is kept, the no-voice ones too: each its own row, written where blv_release_of finds it
        importer = lib.blv_import_firmware if BREAK_UNIT else lib.blv_import_release
        wrong = []
        for k in sorted(found):
            data = open(found[k], "rb").read()
            msg = ctypes.create_string_buffer(256)
            r = importer(data, len(data), out.encode(), msg, 256)
            back = lib.blv_release_of(out.encode()) if os.path.exists(out) else -1
            if r != k or back != k:
                wrong.append("%s -> %d, read back %d" % (table[k]["id"], r, back))
            if os.path.exists(out):
                os.remove(out)
        result(not wrong, "blv_import_release: each of %d releases kept for a unit as its own row%s"
               % (len(found), " (the control: the voices' import)" if BREAK_UNIT else ""), ", ".join(wrong[:4]))
        if BREAK_VOICE or BREAK_UNIT:
            print("releases: %d FAILED" % bad if bad else "releases: every case as expected")
            sys.exit(1 if bad else 0)
    # the control remakes only the voices' releases (both recipe shapes are among them): enough to fail as named
    jobs = [(k, SHAPE[table[k]["shape"]], found[k], os.path.join(tmp, "%s.state" % table[k]["id"]))
            for k in sorted(found) if not BREAK or VOICE.get(table[k]["voice"], -1) >= 0]
    # half the cores: the suite runs timing-sensitive checks alongside (key latency, the open channel)
    with ProcessPoolExecutor(max_workers=max(1, min(len(jobs), (os.cpu_count() or 2) // 2)), initializer=load,
                             initargs=(a.lib, a.chip)) as ex:
        for k, ok, got in ex.map(make, jobs):
            r = table[k]
            how = "answered n (the control)" if BREAK else "%s recipe, %s" % (r["shape"], r["yes"])
            result(ok and got == r["state"], "%s: its state (%s) = the row's" % (r["id"], how),
                   "" if ok and got == r["state"] else (got if not ok else "a different state, %s..." % got[:16]))
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    print("releases: every case as expected" if not bad else "releases: %d FAILED" % bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

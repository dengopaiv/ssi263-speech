"""The Braille Lite unit screen's native part (app/src/main/cpp/ssa_unit.c) on the desktop: built here with the app's
own sources and flags (as build_android.sh builds them into libssi263speech.so), then test_unit_native.c run on the
firmware folder -- and its control, which must fail.

    python src/platforms/android/test/test_unit_native.py [--firmware DIR]

--firmware: default $SSI263_FIRMWARE, else firmware/blazie (BL2ENG.BNS + bl2_2003_warm.state; tns/TNSENG.TNS and a
release's .BNS in a folder below, each checked when there).  Each run gets a fresh scratch folder (a memory left by an
earlier run would be started from).  Exit 0 only when the test passes and the control fails on exactly its check."""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
SRC = os.path.join(ROOT, "src", "csrc")
APP = os.path.join(ROOT, "src", "apps", "blazie")
CPP = os.path.join(ROOT, "src", "platforms", "android", "app", "src", "main", "cpp")
OUT = os.path.join(ROOT, "build", "android_unit_test")
sys.path.insert(0, os.path.join(ROOT, "tools"))


def toolchain():
    if sys.platform == "win32":
        import repo_paths
        bindir = repo_paths.bin_dir("W64DEVKIT")
        return (os.path.join(bindir, "gcc.exe"), os.path.join(bindir, "g++.exe"),
                dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"]))
    return os.environ.get("CC", "cc"), os.environ.get("CXX", "c++"), None


def build():
    cc, cxx, env = toolchain()
    os.makedirs(OUT, exist_ok=True)
    chip = ["-O2", "-std=c99", "-ffp-contract=off"]
    board = ["-O3", "-std=gnu89", "-ffp-contract=off", "-w", "-DBL_Z180_MAME", "-I" + os.path.join(SRC, "blazie"),
             "-I" + os.path.join(SRC, "cpu"), "-I" + SRC]
    z180 = ["-O3", "-std=c++17", "-fno-exceptions", "-fno-rtti", "-ffp-contract=off", "-I" + os.path.join(SRC, "cpu"),
            "-I" + SRC]
    emu = ["-O2", "-std=gnu99", "-ffp-contract=off", "-w", "-I" + APP, "-I" + SRC]     # build_apple.sh's EMU
    front = ["-O2", "-std=gnu99", "-ffp-contract=off", "-Wall", "-Wextra", "-Wno-unused-parameter", "-I" + APP,
             "-I" + SRC, "-I" + CPP]
    units = [(chip, os.path.join(SRC, "ssi263.c")), (chip, os.path.join(SRC, "ssi263dsp.c")),
             (z180, os.path.join(SRC, "cpu", "z180_mame.cpp")), (z180, os.path.join(SRC, "cpu", "z180_asci.cpp"))]
    units += [(board, os.path.join(SRC, "blazie", n + ".c")) for n in (
        "bl_board", "flash29", "bl_serial", "bl_idle", "bl_clock", "bl_rtc6242", "bl_host", "bl_voice", "bl_firmware",
        "bl_state", "tns_board")]
    units += [(emu + ["-I" + os.path.join(SRC, "blazie")], os.path.join(SRC, "blazie", n + ".c"))
              for n in ("bl_files", "bl_files_state", "bl_files_xfer", "fat_img")]
    units += [(emu, os.path.join(APP, n + ".c")) for n in ("emu_unit", "emu_catalog", "tns_setup", "chords", "keys",
                                                           "tns_term")]
    units += [(front, os.path.join(CPP, "ssa_unit.c")), (front, os.path.join(HERE, "test_unit_native.c"))]

    def compile_one(unit):
        flags, src = unit
        obj = os.path.join(OUT, os.path.splitext(os.path.basename(src))[0] + ".o")
        r = subprocess.run([cxx if src.endswith(".cpp") else cc] + flags + ["-c", "-o", obj, src], env=env,
                           capture_output=True, text=True)
        if r.returncode or (src.startswith(CPP) or src.startswith(HERE)) and "warning" in r.stderr:
            sys.exit("compiling %s:\n%s" % (os.path.basename(src), (r.stdout + r.stderr)[-3000:]))
        return obj
    with ThreadPoolExecutor() as pool:
        objs = list(pool.map(compile_one, units))
    exe = os.path.join(OUT, "test_unit_native" + (".exe" if sys.platform == "win32" else ""))
    link = [cxx, "-o", exe] + objs + ["-lm", "-lpthread"]
    if sys.platform == "win32":
        link += ["-static"]
    r = subprocess.run(link, env=env, capture_output=True, text=True)
    if r.returncode:
        sys.exit("linking:\n" + (r.stdout + r.stderr)[-3000:])
    return exe, env


def run(exe, env, firmware, brk=None):
    scratch = tempfile.mkdtemp(prefix="ssi263_unit_")
    e = dict(env or os.environ)
    if brk:
        e["SSI263_UNIT_TEST_BREAK"] = brk
    # 0.8.5's import keeps a release no voice speaks as units/<id>.BNS in the unit folder (FirmwareImport.UnitRelease):
    # a data folder laid out so, with the Braille 'n Speak 640, for the unit screen's "kept release" checks
    bns640 = os.path.join(firmware, "bns640", "june2003", "BSPENG.BNS")
    if os.path.isfile(bns640):
        os.makedirs(os.path.join(scratch, "data", "units"))
        shutil.copyfile(bns640, os.path.join(scratch, "data", "units", "bns640_en_2003_06.BNS"))
    try:
        r = subprocess.run([exe, firmware, scratch], env=e, capture_output=True, text=True, timeout=600)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return r.returncode, r.stdout + r.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--firmware", default=os.environ.get("SSI263_FIRMWARE", os.path.join(ROOT, "firmware", "blazie")))
    a = ap.parse_args()
    exe, env = build()
    code, out = run(exe, env, a.firmware)
    print(out.rstrip())
    code_c, out_c = run(exe, env, a.firmware, "1")
    fails = [ln[4:].strip() for ln in out_c.splitlines() if ln.startswith("FAIL")]   # a check's name may fill its column
    control = code_c != 0 and len(fails) == 1 and fails[0].startswith("keys: the chords the unit gets")
    print("%s control (dots 1 and 4 swapped): %s" % ("ok  " if control else "FAIL",
                                                     ", ".join(f.strip() for f in fails) or "nothing failed"))
    # the files' control: loaded but never written, so the second load cannot find the name (and no key check fails)
    code_f, out_f = run(exe, env, a.firmware, "2")
    ffails = [ln[4:].strip() for ln in out_f.splitlines() if ln.startswith("FAIL")]
    control_f = code_f != 0 and any(f.startswith("files: an existing name asked") for f in ffails) and not any(
        f.startswith("keys") for f in ffails)
    print("%s control (the files never written): %s" % ("ok  " if control_f else "FAIL",
                                                        ", ".join(ffails) or "nothing failed"))
    return 0 if code == 0 and control and control_f else 1


if __name__ == "__main__":
    sys.exit(main())

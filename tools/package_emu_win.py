"""Package the Blazie emulator for Windows alone: blazie-emu-VERSION-windows.zip, the layout of 0.7.x's.

    python src/apps/blazie/build_app.py
    python tools/package_emu_win.py <firmware folder> VERSION

  build/blazie-emu-VERSION-windows.zip
    blazie_emu.exe  blazie_files.exe  README.md  LICENSE
    licenses/Casso-MIT.txt  licenses/MAME-Z180-core-BSD-3-Clause.txt
    firmware/BL2ENG.BNS  firmware/bl2_2003_warm.state
    firmware/spanish/  german/  italian/   each Braille Lite 2000's update file and factory state
    firmware/tns/      the Type 'n Speak's two
    firmware/bns2000/  the Braille 'n Speak 2000's, English and Slovak
    firmware/bl2000/   the Braille Lite 2000's language updates (0.8): 17 firmware files and their states
    firmware/bns640/   the Braille 'n Speak 640's (0.8.5): BSPENG.BNS (June 2003 English), BSPENG_2000.BNS and
                       BSPPLA.BNS (issue #15's September 2000 English and Polish), one folder down where the catalog finds
                       them; no state: the emulator makes a release unit's factory state on its first start.  In the
                       downloads only, never an app's
    build-info.json    the version, the commit, every file's sha256

The firmware folder is the person's own (never in the repository), laid out as firmware/blazie: each file is checked
against the first 16 hex digits of the sha256 Tomi approved, and a missing or changed one stops the packaging.  Then,
from the archive unpacked in a clean folder: the program's imports (Windows' own DLLs only), and every unit booted
headless from the unpacked firmware folder (test_emu_unit; the German unit's key-to-sound bound its own).
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tools import repo_paths  # noqa: E402  (objdump from W64DEVKIT in paths.local, else the PATH)
EMU = os.path.join(ROOT, "nvda", "dist", "blazie-emu")

# (path under firmware/, the first 16 hex digits of the approved sha256)
FIRMWARE = [
    ("BL2ENG.BNS", "a55455ebb8ccc1a9"), ("bl2_2003_warm.state", "fc6dffeff8c4be35"),
    ("spanish/BL2SPA.BNS", "7e0ac26ce6caadc8"), ("spanish/bl2spa_fresh.state", "2ad81f5fe40ba259"),
    ("german/Lite2000.BNS", "945558fe803262d3"), ("german/lite2000_de_fresh.state", "db9b9b165337f9b6"),
    ("italian/Lite2000.BNS", "2af0ebd6de6b6313"), ("italian/lite2000_it_fresh.state", "737b6f224c1be189"),
    ("tns/TNSENG.TNS", "a317fae688f19bbb"), ("tns/TNSSPA.TNS", "78b2cece30545af3"),
    ("bns2000/BS03ENG.BNS", "9ee0af633beb744c"), ("bns2000/bs03eng_fresh.state", "12112afda9be2809"),
    ("bns2000/BS2SLL.BNS", "8c01c59845b5609c"), ("bns2000/bs2sll_fresh.state", "6818720dc50c5f7d"),
]
# the Braille 'n Speak 640 (0.8.5): (its name in the archive's firmware/bns640/, the file in the firmware folder and
# its sha256's first 16 hex digits, the factory state the tests boot it from and its, the catalog's id, the label,
# the key-to-sound bound or None).  The state is only the test's: the emulator makes its own on the first start.
BNS640 = [
    ("BSPENG.BNS", "bns640/june2003/BSPENG.BNS", "ff0738fe2b041fc6", "bns640/june2003/bspeng_fresh.state",
     "f9987f05ead89ff8", "bns640_en_2003_06", "Braille 'n Speak 640 English", None),
    ("BSPENG_2000.BNS", "bns640/issue15/BSPENG.BNS", "ea6d9f069ce4d86f", "bns640/issue15/bspeng_2000_fresh.state",
     "ada323ad7d97ff38", "bns640_en_2000_09", "Braille 'n Speak 640 English, September 2000", None),
    ("BSPPLA.BNS", "bns640/issue15/bsppla.bns", "5aca4a6e5da5bbe5", "bns640/issue15/bsppla_fresh.state",
     "f3cb8f9abbb82246", "bns640_pl_2000_09", "Braille 'n Speak 640 Polish", "480"),
]
# (the unit, firmware, state -- None: the Type 'n Speak, from cold --, key-to-sound bound in ms or None: the test's)
UNITS = [("English", "BL2ENG.BNS", "bl2_2003_warm.state", None),
         ("Spanish", "spanish/BL2SPA.BNS", "spanish/bl2spa_fresh.state", None),
         ("German", "german/Lite2000.BNS", "german/lite2000_de_fresh.state", "450"),
         ("Italian", "italian/Lite2000.BNS", "italian/lite2000_it_fresh.state", None),
         ("Braille 'n Speak 2000 English", "bns2000/BS03ENG.BNS", "bns2000/bs03eng_fresh.state", None),
         ("Braille 'n Speak 2000 Slovak", "bns2000/BS2SLL.BNS", "bns2000/bs2sll_fresh.state", "480"),
         ("Type 'n Speak English", "tns/TNSENG.TNS", None, None),
         ("Type 'n Speak Spanish", "tns/TNSSPA.TNS", None, None)]
SYSTEM_DLLS = {"kernel32.dll", "msvcrt.dll", "user32.dll", "gdi32.dll", "winmm.dll", "comdlg32.dll", "setupapi.dll",
               "advapi32.dll", "shell32.dll", "ole32.dll", "comctl32.dll"}


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def fail(msg):
    print("FAIL " + msg)
    sys.exit(1)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    fw, version = os.path.abspath(sys.argv[1]), sys.argv[2]
    approved = {}
    for name, want in FIRMWARE:
        p = os.path.join(fw, name)
        if not os.path.isfile(p):
            fail("no %s in %s" % (name, fw))
        got = sha256(p)
        if not got.startswith(want):
            fail("%s is not the approved file (sha256 %s..., want %s...)" % (name, got[:16], want))
        approved[name] = got
    for _, name, want, state, state_want, _, _, _ in BNS640:
        for f, w in ((name, want), (state, state_want)):
            got = sha256(os.path.join(fw, f)) if os.path.isfile(os.path.join(fw, f)) else "missing"
            if not got.startswith(w):
                fail("%s is not the approved file (sha256 %s..., want %s...)" % (f, got[:16], w))

    commit = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "--", "src/apps/blazie", "src/csrc"],
                           capture_output=True, text=True).stdout.strip()
    if dirty:
        fail("the emulator's sources have uncommitted changes: the archive must be a commit's\n" + dirty)
    files = [("blazie_emu.exe", os.path.join(EMU, "blazie_emu.exe")),
             ("blazie_files.exe", os.path.join(EMU, "blazie_files.exe")),
             ("README.md", os.path.join(ROOT, "src", "apps", "blazie", "README.md")),
             ("LICENSE", os.path.join(ROOT, "LICENSE")),
             ("licenses/Casso-MIT.txt", os.path.join(ROOT, "third_party", "casso", "LICENSE")),
             ("licenses/MAME-Z180-core-BSD-3-Clause.txt",
              os.path.join(ROOT, "src", "csrc", "cpu", "mame_z180", "LICENSE-BSD-3-Clause.txt"))]
    files += [("firmware/" + name, os.path.join(fw, name)) for name, _ in FIRMWARE]
    files += [("firmware/bns640/" + arc, os.path.join(fw, name)) for arc, name, _, _, _, _, _, _ in BNS640]
    # the Braille Lite 2000's language updates (0.8): firmware/bl2000/, each file byte for byte the published NVDA
    # add-on's copy (the catalog finds them one folder down, as the Linux archive's share/ssi263-speech/bl2000/)
    addon = os.path.join(ROOT, "nvda", "dist", "ssi263-speech-%s.nvda-addon" % version)
    if not os.path.isfile(addon):
        fail("no %s: its bl2000/ files are the ones this archive must carry" % addon)
    with zipfile.ZipFile(addon) as z:
        theirs = {n.rsplit("/", 1)[1]: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()
                  if "/_ssi263_blazie/bl2000/" in n and not n.endswith("/")}
    ours = sorted(os.listdir(os.path.join(fw, "bl2000"))) if os.path.isdir(os.path.join(fw, "bl2000")) else []
    if sorted(theirs) != [n for n in ours if n in theirs] or len(theirs) != 34:
        fail("bl2000/: the add-on has %d files, the firmware folder %d of them" % (len(theirs), sum(n in theirs for n in ours)))
    for n in sorted(theirs):
        if sha256(os.path.join(fw, "bl2000", n)) != theirs[n]:
            fail("bl2000/%s differs from the add-on's" % n)
        files.append(("firmware/bl2000/" + n, os.path.join(fw, "bl2000", n)))
    for _, src in files:
        if not os.path.isfile(src):
            fail("missing " + src)
    info = {"version": version, "runtime_source_commit": commit, "cpu": "MAME Z180", "packaged_by": "Claude",
            "files_sha256": {arc: sha256(src) for arc, src in files}}
    out = os.path.join(ROOT, "build", "blazie-emu-%s-windows.zip" % version)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, src in files:
            z.write(src, arc)
        z.writestr("build-info.json", json.dumps(info, indent=2) + "\n")
    print("wrote %s (%.1f MB), commit %s" % (out, os.path.getsize(out) / 1e6, commit[:7]))

    # from a clean folder: the archive as a person unpacks it
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(out) as z:
            z.extractall(tmp)
        for arc, want in info["files_sha256"].items():
            if sha256(os.path.join(tmp, arc)) != want:
                print("FAIL unpacked %s differs" % arc)
                ok = False
        objdump = repo_paths.program("W64DEVKIT", "objdump")
        for exe in ("blazie_emu.exe", "blazie_files.exe"):
            dump = subprocess.run([objdump, "-p", os.path.join(tmp, exe)], capture_output=True, text=True).stdout
            dlls = {l.split(":", 1)[1].strip().lower() for l in dump.splitlines() if "DLL Name:" in l}
            extra = dlls - SYSTEM_DLLS
            print("%s  %s imports %s" % ("ok  " if not extra else "FAIL", exe, ", ".join(sorted(dlls))))
            ok &= not extra
        for label, fwf, st, bound in UNITS:
            cmd = [os.path.join(EMU, "test_emu_unit.exe"), "bl" if st else "tns", os.path.join(tmp, "firmware", fwf),
                   os.path.join(tmp, "firmware", st) if st else "-"] + ([bound] if bound else [])
            r = subprocess.run(cmd, capture_output=True, text=True)
            last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
            print("%s  %s, headless from the archive: %s" % ("ok  " if r.returncode == 0 else "FAIL", label, last))
            ok &= r.returncode == 0
        # the 640s: the archive's firmware booted from its approved factory state, and the catalog offering each
        # from the unpacked firmware folder as the program's menu does
        for arc, _, _, state, _, _, label, bound in BNS640:
            r = subprocess.run([os.path.join(EMU, "test_emu_unit.exe"), "bl",
                                os.path.join(tmp, "firmware", "bns640", arc), os.path.join(fw, state)]
                               + ([bound] if bound else []), capture_output=True, text=True)
            last = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
            print("%s  %s, headless from the archive: %s" % ("ok  " if r.returncode == 0 else "FAIL", label, last))
            ok &= r.returncode == 0
        listed = subprocess.run([os.path.join(EMU, "test_catalog.exe"), os.path.join(tmp, "firmware"), "--list"],
                                capture_output=True, text=True).stdout.splitlines()
        for _, _, _, _, _, key, label, _ in BNS640:
            there = any(l.startswith("unit %s 1 " % key) for l in listed)
            print("%s  %s in the emulator's menu from the archive (%s)" % ("ok  " if there else "FAIL", label, key))
            ok &= there
    print("package: all passed" if ok else "package: FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

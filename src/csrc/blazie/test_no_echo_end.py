"""The units that never echo ^F end when their firmware does (bl_host.c no_echo_finished), and never earlier: after
the first "done" the SAME unit runs on for ON_S more, with nothing sent, cancelled or reset, and no spoken phoneme may
follow (a pause load, code 00, is not speech; the last sound decaying is not a load).  Every speaking non-echoing
Braille Lite and Braille 'n Speak 2000 release whose firmware is in the firmware folder -- the shipped Italian and
Slovak among them, which test_release_voices leaves to their own tests -- three sentences each, at host blocks of 3,
15.5 and 30 ms (the lockstep's 0.5 ms grain kept).  After Astra's independent harness (Reply 248, review248): 63
continuations, none spoke on.

test_release_voices times "done" against the last sound (too LATE); this one catches done too EARLY, which a
latency check cannot: a sentence cut short ends quickly too.

    python test_no_echo_end.py [--firmware DIR] [--lib PATH] [--chip PATH]

    SSI263_NO_ECHO_END_BREAK=early   control: "done" taken 0.8 s into each first sentence, whatever bh_busy says --
                                     the speech that follows must be caught (Astra's early control)
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
sys.path.insert(0, os.path.join(REPO, "src"))
import gen_languages  # noqa: E402
import test_releases  # noqa: E402

WINDOWS = sys.platform == "win32"
BREAK = os.environ.get("SSI263_NO_ECHO_END_BREAK", "")
ON_S = 1.5                       # the unit runs on this long after its first done
LIMIT_S = 30.0                   # a sentence not done by then fails
TEXTS = [("Hello. One two three.", 0.003),
         ("Select synthesizer dialog. Rate 50. Pitch 65.", 0.0155),
         ("Seventeen, seventy, and seventeen hundred. Feeling fine, thank you.", 0.030)]
args = None


def load(lib_path, chip_path):
    global args
    args = (lib_path, chip_path)
    if chip_path:
        os.environ["SSI263_LIB"] = chip_path
    test_releases.load(lib_path, chip_path)


def run(job):
    """In a worker: (row, its id, firmware, state path, slow boot) -> lines of results, failures counted."""
    from hosts.native_blazie import NativeBlazie
    from ssi263.native import SSI263C
    k, rid, fw, st, slow = job
    err = ctypes.create_string_buffer(300)
    if not test_releases.lib.blv_make_release_state(fw.encode(), k, st.encode(), test_releases.PROGRESS(0), None,
                                                    err, 300):
        return ["FAIL %s: state: %s" % (rid, err.value.decode(errors="replace"))], 1
    writes = []
    h = NativeBlazie(args[0], fw, st, chip=SSI263C(out_rate=22050), menu=("punct_none", "numbers_toggle"),
                     key_start=8000000 if slow else 3000000, key_gap=10000000 if slow else 1500000,
                     on_write=lambda t, r, v: writes.append((t, r, v)))
    h.no_echo = 1
    h.send("\x18\r\x06")
    h.run(0.3)
    h.send("\x056V")
    h.run(0.05)
    out, bad = [], 0
    for j, (text, block) in enumerate(TEXTS):
        if BREAK == "early" and j:
            break
        del writes[:]
        h.say(text)
        start = h.chip.time
        done, until, mark = None, LIMIT_S, 0
        while h.chip.time - start < until:
            h.run(block)
            now = h.chip.time - start
            busy = h.busy() and not (BREAK == "early" and now >= 0.8)
            if not busy and done is None:
                done, until, mark = now, now + ON_S, len(writes)
        spoken = sum(1 for _t, r, v in writes if r == 0 and v & 63)
        after = sum(1 for _t, r, v in writes[mark:] if r == 0 and v & 63) if done is not None else 0
        ok = done is not None and spoken > 0 and after == 0
        if done is None:
            what = "not done in %.0f s" % LIMIT_S
        elif after:
            what = "done at %.2f s, then %d spoken phonemes in the next %.1f s: ended EARLY" % (done, after, ON_S)
        else:
            what = "done at %.2f s, %d spoken phonemes, none in the %.1f s after" % (done, spoken, ON_S)
        out.append("%-4s %s, %d (%.1f ms blocks): %s" % ("ok" if ok else "FAIL", rid, j + 1, block * 1000, what))
        bad += not ok
    h.close()
    os.remove(st)
    return out, bad


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
    tmp = tempfile.mkdtemp(prefix="ssi263-no-echo-end-")
    jobs = [(k, table[k]["id"], found[k], os.path.join(tmp, "%s.state" % table[k]["id"]), table[k]["boot"] == "slow")
            for k in sorted(found) if table[k]["echo"] == "no" and table[k]["speaks"] == "yes"
            and table[k]["model"] in ("bl", "bns")]
    if BREAK == "early":
        jobs = jobs[:1]
    if not jobs:
        print("skip: no non-echoing release's firmware in %s" % a.firmware)
        sys.exit(0)
    bad = 0
    with ProcessPoolExecutor(max_workers=max(1, min(len(jobs), (os.cpu_count() or 2) // 2)), initializer=load,
                             initargs=(a.lib, a.chip)) as ex:
        for lines, n in ex.map(run, jobs):
            for line in lines:
                print(line)
            bad += n
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    print("no-echo end: %d units, every done final" % len(jobs) if not bad else "no-echo end: %d FAILED" % bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

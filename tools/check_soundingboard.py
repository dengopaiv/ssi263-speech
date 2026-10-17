"""The Sounding Board's front end is the Speak-Out's: GW Micro's DOS drivers (SBLOAD.COM + SB.COM 2.7, run by
src/hosts/soundingboard.py on MAME's 8086) and the Speak-Out's SPEAKOUT.HEX (src/hosts/speakout.py's SpeakOutV40), fed
the same text, send the chip the same frames, register for register and in the same order (the Speak-Out's idle frames between
utterances left out) -- the 2026-10-09 finding
(134 and 381 frames), kept as a test.  Timing is each board's own and is not compared.

Each host boots and finishes whatever it says at start-up; then each sentence is said and run until the host is idle,
and the writes from the say on are compared.  Firmware: firmware/gw-micro-sounding-board/{SBLOAD.COM,SB.COM} and
firmware/gw-micro-speakout/SPEAKOUT.HEX (none is in the repository: skipped, said so, when absent).

    python tools/check_soundingboard.py            exit 1 on any failure

Control (SB_CHECK_BREAK=1): the Sounding Board is given each sentence without its last word -- every sentence must
differ.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
from hosts.soundingboard import SoundingBoard      # noqa: E402
from hosts.speakout import SpeakOutV40              # noqa: E402

SB_DIR = os.path.join(ROOT, "firmware", "gw-micro-sounding-board")
HEX = os.path.join(ROOT, "firmware", "gw-micro-speakout", "SPEAKOUT.HEX")
TEXTS = ["Hello, this is the Sounding Board.",
         "The quick brown fox jumps over the lazy dog, 1234 times.",
         "Doctor Smith's appointment is at 3:45 PM on Tuesday."]
BREAK = os.environ.get("SB_CHECK_BREAK") == "1"


def quiet(host, limit=20.0):
    t = 0.0
    while host.busy() and t < limit:
        host.run(0.05)
        t += 0.05


def speech(writes):
    """the writes grouped into frames (a frame ends at its phoneme: R0 written non-zero), with the Speak-Out's idle
    frames left out -- between utterances it sends PA forever at rate F, which speech never uses (speakout.py)"""
    out, frame, r2 = [], [], 0
    for r, v in writes:
        frame.append((r, v))
        if r == 2:
            r2 = v
        if r == 0 and v != 0:
            if not (v & 0x3F == 0 and r2 >> 4 == 0xF):
                out.append(tuple(frame))
            frame = []
    return out


def frames(host, writes, text):
    n0 = len(writes())
    host.say(text + "\r")
    host.run(0.05)
    quiet(host)
    return speech([(r, v) for _, r, v in writes()[n0:]])


def main():
    paths = [os.path.join(SB_DIR, "SBLOAD.COM"), os.path.join(SB_DIR, "SB.COM"), HEX]
    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        print("skip  the Sounding Board check: no %s" % ", ".join(os.path.relpath(p, ROOT) for p in missing))
        return 0
    sb = SoundingBoard(paths[0], paths[1])
    sb.boot()
    quiet(sb)
    so = SpeakOutV40(HEX)
    so.boot()
    quiet(so)
    failures = 0
    for text in TEXTS:
        a = frames(so, lambda: so.chip_writes, text)
        b = frames(sb, lambda: sb.writes, text.rsplit(" ", 1)[0] + "." if BREAK else text)
        same = a == b and len(a) > 10
        where = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
        print("%-5s %-58s %d frames (Speak-Out) / %d (Sounding Board)%s" % (
            "ok" if same else "FAIL", text, len(a), len(b), "" if same else ", first difference at frame %d" % where))
        failures += not same
    print("sounding board: %s" % ("every sentence the Speak-Out's, write for write" if not failures
                                  else "%d FAILED" % failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

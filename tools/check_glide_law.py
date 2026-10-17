"""The mode-3 glide law (params glide_field_mult = 8 / (8 - G), engine v0.20): the pitch moves one I count per
16 (8 - G)(16 - R) XCK cycles, as measured on Tomi's chip (REG_claude_glide, letter 206; Astra, Reply 208).

  LAW, Python reference and C core, in the chip's own state: mode 3, AH held, rate R; the pitch settled at R1's
  count 16, then R1 rewritten to count 24 (up) and back to 16 (down) in each glide field G 0-7.  The time the
  transitioned pitch takes to arrive, sampled every 0.25 ms, gives its rate in I counts per second, which must be
  xck / (16 (8 - G)(16 - R)) within TOL.
  PARITY: Python and C arrive at the same sample in every case.

    python tools/check_glide_law.py            exit 1 on any failure

Control (GLIDE_LAW_BREAK=v019): v0.19's table (1, 0.962, 1.226, 2.462, 2.092, 2.462, 2.462, 2.462) -- every field
but 0 must fail, in both engines.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
from ssi263.chip import SSI263          # noqa: E402
from ssi263.native import SSI263C       # noqa: E402

FS = 44100
RATE = 12
STEP = 0.00025
TOL = 0.01
V019 = (1.0, 0.962, 1.226, 2.462, 2.092, 2.462, 2.462, 2.462)
PARAMS = {"glide_field_mult": V019} if os.environ.get("GLIDE_LAW_BREAK") == "v019" else {}
failures = []


def ok(cond, name, detail):
    print("%-5s %-34s %s" % ("ok" if cond else "FAIL", name, detail))
    if not cond:
        failures.append(name)


def pitch(chip):
    if isinstance(chip, SSI263C):
        s = chip.state()
        return s[2], s[3]
    return chip.trans, chip.trans_target


def arrival(chip, r1):
    """write R1 and return (seconds until the pitch reaches its target, counts moved)"""
    start, _ = pitch(chip)
    chip.write(1, r1)
    _, target = pitch(chip)
    t = 0.0
    while abs(pitch(chip)[0] - target) > 1e-9:
        chip.run(STEP)
        t += STEP
        if t > 3.0:
            return None, abs(target - start)
    return t, abs(target - start)


def main():
    arrivals = {}
    for tag, make in (("py", lambda: SSI263(PARAMS, out_rate=FS)), ("C", lambda: SSI263C(PARAMS, out_rate=FS))):
        for g in range(8):
            chip = make()
            ah = next(k for k, v in chip.rom.names.items() if v == "AH")
            for r, v in ((3, 0x80), (0, 0xC0), (3, 0x70), (2, RATE << 4), (4, 0xE7), (1, (16 << 3) | 7), (3, 0x73),
                         (0, ah)):
                chip.write(r, v)
            chip.run(0.2)                                       # settled at count 16 x 64 (field 7, fast)
            xck = chip.p["xck_hz"] if hasattr(chip, "p") and isinstance(chip.p, dict) else 1e6
            want = xck / (16.0 * (8 - g) * (16 - RATE))
            for direction, r1 in (("up", (24 << 3) | g), ("down", (16 << 3) | g)):
                t, moved = arrival(chip, r1)
                arrivals[(tag, g, direction)] = t
                if t is None:
                    ok(False, "LAW %s field %d %s" % (tag, g, direction), "never arrived")
                    continue
                got = moved / t
                ok(abs(got / want - 1) <= TOL + STEP / t, "LAW %s field %d %s" % (tag, g, direction),
                   "%.0f counts in %.2f ms: %.1f counts/s, the law %.1f (%+.1f%%)"
                   % (moved, 1000 * t, got, want, 100 * (got / want - 1)))
    same = all(arrivals[("py",) + k[1:]] == arrivals[k] for k in arrivals if k[0] == "C")
    ok(same, "PARITY: Python = C", "every field and direction arrives at the same step" if same else
       "they differ")
    print("glide law: %s" % ("all passed" if not failures else "%d FAILED" % len(failures)))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

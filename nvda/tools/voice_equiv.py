"""The gate for bl_voice (src/csrc/blazie/bl_voice.c): the real NVDA Braille Lite driver, under the stand-in NVDA,
and the C voice speak the same texts with the same settings, and every PCM byte the driver feeds its player must
equal what blv_render returns.  English and (when its files are there) Spanish; line splitting and packing, the
text clean-up, settings changes and the lead trim are all on the path.  0.8: the German, Italian and Slovak units
(each when its files are there): their code pages (850, 852), and the Italian and Slovak units' end without ^F
echoes (bl_host.c "no_echo").

    python voice_equiv.py            # exit 1 on the first difference
    python voice_equiv.py --run-ahead
                                     # "run ahead" on: the driver's runAhead setting against blv_set_run_ahead (the
                                     # host runs ahead only with packing on, as the driver gates it; English and
                                     # Spanish only, as the driver and voices.c have it -- the German unit is not
                                     # asked; the Italian and Slovak units ARE, in C, and must not: no ^F echo ends
                                     # a capture there (bl_host.c's gate; without it they ran on for minutes))
    VOICE_EQUIV_BREAK=1              # control: the C side speaks with pack flipped -- must FAIL
    VOICE_EQUIV_BREAK=ahead          # control, with --run-ahead: the C side never turns run ahead on -- must FAIL

Number words are off on both sides: bl_voice v1 leaves numbers to the firmware (bl_voice.h).
"""
import ctypes
import os
import struct
import sys
import time

# a text's letters the console lacks (Slovak) must never stop the report
sys.stdout.reconfigure(errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
RUN_AHEAD = "--run-ahead" in sys.argv
sys.argv = [sys.argv[0], "blazie"]
src = open(os.path.join(HERE, "fake_nvda_driver_test.py"), encoding="utf-8").read()
exec(src.split("time.sleep(2.0)")[0])

ENG = os.path.dirname(drv_mod.FIRMWARE)
ARCH = "x64" if struct.calcsize("P") == 8 else "x86"
LIB = os.path.join(os.path.dirname(HERE), "dist", "blazie-lib", ARCH, "bl.dll")
CHIP = os.path.join(os.path.dirname(os.path.dirname(HERE)), "src", "ssi263", "_bin", ARCH, "ssi263.dll")
BREAK = os.environ.get("VOICE_EQUIV_BREAK") == "1"
BREAK_AHEAD = os.environ.get("VOICE_EQUIV_BREAK") == "ahead"

# (text, rate, pitch, tone, volume, pack)
CASES = [
    ("Hello there.", 50, 50, 7, 100, True),
    ("Custom number processing check box checked", 50, 50, 7, 100, True),
    ("This is a longer sentence, with a comma early on, that keeps going well past the fourteen word limit of "
     "the unit. Second sentence here! And a third? Yes. Short one. Another short one.", 50, 50, 7, 100, True),
    ("It’s “quoted” text – with dashes… café and an emoji \U0001F389 too.",
     50, 50, 7, 100, True),
    ("Faster, lower and quieter now.", 70, 30, 12, 60, True),
    ("This is a longer sentence, with a comma early on, that keeps going well past the fourteen word limit of "
     "the unit. Second sentence here! And a third? Yes. Short one. Another short one.", 50, 50, 7, 100, False),
    ("Room 12, $3.50 and 1,234,567 items.", 50, 50, 7, 100, True),
    ("a. b  c\td\n\ne. f", 20, 90, 3, 100, True),
    ("OK button", 100, 0, 26, 100, True),
]
CASES_ES = [("Mañana, ¿qué tal? Él está aquí. ¡Olé!", 50, 50, 7, 100, True),
            ("Ángel e Íñigo, Óscar y Úrsula.", 50, 50, 7, 100, True)]
# voice id, its firmware and state attributes, encoding (bl_voice.h), its cases
CASES_MORE = [
    ("blazie_de", "FIRMWARE_DE", "STATE_DE", 1,
     [("Guten Tag! Wie geht es Ihnen? Grüße aus der Straße, schön.", 50, 50, 7, 100, True),
      ("Ein längerer Satz, mit einem Komma, der weit über die vierzehn Wörter hinausgeht, die das Gerät auf einmal liest. Noch einer.", 60, 40, 9, 80, False)]),
    ("blazie_it", "FIRMWARE_IT", "STATE_IT", 14,
     [("Buongiorno, come stai? La città è bella, perché sì. È vero, Òscar.", 50, 50, 7, 100, True),
      ("Più tardi, così è.", 70, 30, 12, 60, True)]),
    ("blazie_sk", "FIRMWARE_SK", "STATE_SK", 7,
     [("Dobrý deň, ako sa máš? Toto je slovenský hlas, čaj a šach.", 50, 50, 7, 100, True),
      ("Žltý kôň úpel ďábelské ódy.", 50, 50, 7, 100, False)]),
]


def driver_side(cases):
    global mark
    out = []
    raw = []
    orig = d._player.feed

    def feed(data, onDone=None):
        if data:
            raw.append(bytes(data))
        return orig(data, onDone)
    d._player.feed = feed
    d._numbers = False
    d._set_runAhead(RUN_AHEAD)
    for text, rate, pitch, tone, volume, pack in cases:
        d._rate, d._pitch, d._tone, d._volume, d._short = rate, pitch, str(tone), volume, pack
        del raw[:]
        mark = len(notified)
        d.speak([text])
        if not wait_idle(60):
            sys.exit("the driver did not finish %r: %s" % (text, last_wait_error[0]))
        out.append((b"".join(raw), d._unit.geti("run_ahead")))
    d._player.feed = orig
    return out


def c_side(cases, fw, state, encoding, no_echo=False, ahead=RUN_AHEAD):
    ctypes.CDLL(CHIP)                                   # bl.dll imports it: load that copy first
    lib = ctypes.CDLL(LIB)
    lib.blv_create.restype = ctypes.c_void_p
    lib.blv_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_double, ctypes.c_int,
                               ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    lib.blv_set.argtypes = [ctypes.c_void_p] + [ctypes.c_int] * 5
    lib.blv_speak.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    lib.blv_render.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_short)),
                               ctypes.POINTER(ctypes.c_int)]
    lib.blv_destroy.argtypes = [ctypes.c_void_p]
    lib.blv_host.restype = ctypes.c_void_p
    lib.blv_host.argtypes = [ctypes.c_void_p]
    lib.bh_get_int.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    err = ctypes.create_string_buffer(256)
    v = lib.blv_create(fw.encode("mbcs"), state.encode("mbcs"), encoding, float(d._out_rate), 1, 0, err, 256)
    if not v:
        sys.exit("blv_create: %s" % err.value.decode())
    if ahead and not BREAK_AHEAD:
        lib.blv_set_run_ahead.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.blv_set_run_ahead(v, 1)
    host = lib.blv_host(v)
    if no_echo:                                         # as voices.c sets it for these units
        lib.bh_set_int.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        lib.bh_set_int(host, b"no_echo", 1)
    out = []
    for text, rate, pitch, tone, volume, pack in cases:
        lib.blv_set(v, rate, pitch, tone, volume, int(pack) ^ (1 if BREAK else 0))
        lib.blv_speak(v, text.encode("utf-8"))
        pcm, done, chunks = ctypes.POINTER(ctypes.c_short)(), ctypes.c_int(0), []
        while not done.value:
            n = lib.blv_render(v, ctypes.byref(pcm), ctypes.byref(done))
            if n:
                chunks.append(ctypes.string_at(pcm, 2 * n))
        ahead = lib.bh_get_int(host, b"run_ahead")
        if ahead and lib.bh_get_int(host, b"run_ahead_captured") <= 0:
            ahead = -1                                  # on, but nothing captured: not the run-ahead path
        out.append((b"".join(chunks), ahead))
    lib.blv_destroy(v)
    return out


def compare(label, cases, a, b, ahead_lang=True, gated=False):
    """ahead_lang: the voice runs ahead at all (English, Spanish); gated: C was asked to and the host must refuse
    (on, nothing captured: -1, taken as off)"""
    bad = 0
    for (text, *_, pack), (x, xa), (y, ya) in zip(cases, a, b):
        want = int(RUN_AHEAD and pack and ahead_lang)   # the driver runs ahead only with short pauses on
        if gated and ya == -1:
            ya = 0
        flags = "" if xa == want and ya == want else "  run ahead: driver %d, C %d, want %d" % (xa, ya, want)
        if x == y and not flags:
            print("same  %-6s %6d samples  run ahead %d  %r" % (label, len(x) // 2, want, text[:40]))
            continue
        bad += 1
        if x == y:
            print("DIFF  %-6s %6d samples, the same PCM%s  %r" % (label, len(x) // 2, flags, text[:40]))
            continue
        k = next((i for i in range(0, min(len(x), len(y)), 2) if x[i:i + 2] != y[i:i + 2]), min(len(x), len(y)))
        print("DIFF  %-6s driver %d / C %d samples, first difference at sample %d%s  %r"
              % (label, len(x) // 2, len(y) // 2, k // 2, flags, text[:40]))
    return bad


while d._unit is None:
    time.sleep(0.05)
bad = compare("en", CASES, driver_side(CASES), c_side(CASES, drv_mod.FIRMWARE, drv_mod.STATE, 0))
if os.path.isfile(drv_mod.FIRMWARE_ES) and os.path.isfile(drv_mod.STATE_ES):
    d._set_voice("blazie_es")
    bad += compare("es", CASES_ES, driver_side(CASES_ES), c_side(CASES_ES, drv_mod.FIRMWARE_ES, drv_mod.STATE_ES, 13))
more = 0
for voice, fw_attr, st_attr, enc, cases in CASES_MORE:
    fw, st = getattr(drv_mod, fw_attr), getattr(drv_mod, st_attr)
    if os.path.isfile(fw) and os.path.isfile(st):
        d._set_voice(voice)
        no_echo = voice in drv_mod.NO_ECHO
        force = RUN_AHEAD and no_echo                   # asked in C anyway: the host's gate must hold
        bad += compare(voice[7:], cases, driver_side(cases), c_side(cases, fw, st, enc, no_echo, ahead=force),
                       ahead_lang=False, gated=force)
        more += len(cases)
d.terminate()
total = len(CASES) + len(CASES_ES) + more
print("%d of %d utterances byte-identical to the NVDA driver%s" % (total - bad, total,
                                                                   " (run ahead on)" if RUN_AHEAD else ""))
sys.exit(1 if bad else 0)

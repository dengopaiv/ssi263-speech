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

  word    (the Arabic (UAE) unit) whole words with their vowel marks, a tatweel, a hamza and digits: the bytes it gets

Control (SSI263_LETTERS_BREAK=1): each voice sends what it did before these tables (plain letters, plain 852 or 850),
so the Hungarian vowels, the Czech and Scandinavian letters, the Slovak o circumflex, the capitals the Polish,
Croatian and French units skip and the Arabic (UAE) unit's letters and words fail.  This test must then fail.
"""
import argparse
import ctypes
import os
import struct
import sys
import tempfile
import unicodedata
from concurrent.futures import ProcessPoolExecutor

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
    # Spain's Spanish, the Italian, Turkish, Portuguese and Russian units (2026-10-16)
    "bl2_es_2000_09": (13, 1, "sa{}sa", {
        "\u00e1": (0xA0, "S PA AH1 PA AH1 PA S PA AH1 PA"),
        "\u00c1": (0xA0, "S PA AH1 PA AH1 PA S PA AH1 PA"),
        "\u00e9": (0x82, "S PA AH1 PA E1 PA S PA AH1 PA"),
        "\u00c9": (0x90, "S PA AH1 PA E1 PA S PA AH1 PA"),
        "\u00ed": (0xA1, "S PA AH1 PA Y PA S PA AH1 PA"),
        "\u00cd": (0xA1, "S PA AH1 PA Y PA S PA AH1 PA"),
        "\u00f3": (0xA2, "S PA AH1 PA O PA S PA AH1 PA"),
        "\u00d3": (0xE0, "S PA AH1 PA O PA S PA AH1 PA"),
        "\u00fa": (0xA3, "S PA AH1 PA U1 PA S PA AH1 PA"),
        "\u00da": (0xE9, "S PA AH1 PA U1 PA S PA AH1 PA"),
        "\u00fc": (0x81, "S PA AH1 PA W PA S PA AH1 PA"),
        "\u00dc": (0x9A, "S PA AH1 PA W PA S PA AH1 PA"),
        "\u00f1": (0xA4, "S PA AH1 PA N PA Y1 PA S PA AH1 PA"),
        "\u00d1": (0xA5, "S PA AH1 PA N PA Y1 PA S PA AH1 PA"),
    }),
    "bl2_it_2000_09": (14, 1, "sa{}sa", {
        "\u00e0": (0x85, "S PA AH1 PA AH1 PA S PA AH1 PA"),
        "\u00c0": (0x85, "S PA AH1 PA AH1 PA S PA AH1 PA"),
        "\u00e8": (0x8A, "S PA AH1 PA E1 PA S PA AH1 PA"),
        "\u00c8": (0x8A, "S PA AH1 PA E1 PA S PA AH1 PA"),
        "\u00e9": (0x82, "S PA AH1 PA E1 PA S PA AH1 PA"),
        "\u00c9": (0x90, "S PA AH1 PA E1 PA S PA AH1 PA"),
        "\u00ec": (0x8D, "S PA AH1 PA Y PA S PA AH1 PA"),
        "\u00cc": (0x8D, "S PA AH1 PA Y PA S PA AH1 PA"),
        "\u00ed": (0xA1, "S PA AH1 PA Y PA S PA AH1 PA"),
        "\u00cd": (0xA1, "S PA AH1 PA Y PA S PA AH1 PA"),
        "\u00f2": (0x95, "S PA AH1 PA O PA S PA AH1 PA"),
        "\u00d2": (0x95, "S PA AH1 PA O PA S PA AH1 PA"),
        "\u00f3": (0xA2, "S PA AH1 PA O PA S PA AH1 PA"),
        "\u00d3": (0xE0, "S PA AH1 PA O PA S PA AH1 PA"),
        "\u00f9": (0x97, "S PA AH1 PA U1 PA S PA AH1 PA"),
        "\u00d9": (0x97, "S PA AH1 PA U1 PA S PA AH1 PA"),
        "\u00fa": (0xA3, "S PA AH1 PA U1 PA S PA AH1 PA"),
        "\u00da": (0xE9, "S PA AH1 PA U1 PA S PA AH1 PA"),
        "\u00ee": (None, None),
        "\u00ce": (None, None),
    }),
    "bl2_tr_1998_12": (15, 3, "sa{}sa", {
        "\u00e7": (0x87, "S PA AH1 PA T PA SCH PA S PA AH1 PA"),
        "\u00c7": (0x87, "S PA AH1 PA T PA SCH PA S PA AH1 PA"),
        "\u011f": (0xA7, "S PA AH1 PA LF PA S PA AH1 PA"),
        "\u011e": (0xA6, "S PA AH1 PA LF PA S PA AH1 PA"),
        "\u00f6": (0x94, "S PA AH1 PA ER PA S PA AH1 PA"),
        "\u00d6": (0x99, "S PA AH1 PA ER PA S PA AH1 PA"),
        "\u015f": (0x9F, "S PA AH1 PA SCH PA S PA AH1 PA"),
        "\u015e": (0x9E, "S PA AH1 PA SCH PA S PA AH1 PA"),
        "\u00fc": (0x81, "S PA AH1 PA :U PA S PA AH1 PA"),
        "\u00dc": (0x9A, "S PA AH1 PA :U PA S PA AH1 PA"),
        "\u0130": (None, "=i"),     # sent as i
        "\u0131": (0x8D, "S PA AH1 PA ER PA S PA AH1 PA"),
        "\u00e2": (None, None),
        "\u00c2": (None, None),
        "\u00ee": (None, None),
        "\u00ce": (None, None),
        "\u00fb": (None, None),
        "\u00db": (None, None),
    }),
    "bl2_pt_1998_12": (16, 4, "sa{}sa", {
        "\u00e1": (0xA0, "S PA S PA AH1 PA AH1 PA Z PA AH1 PA"),
        "\u00c1": (0xA0, "S PA S PA AH1 PA AH1 PA Z PA AH1 PA"),
        "\u00e2": (0x83, "S PA S PA AH1 PA AH1 PA Z PA AH1 PA"),
        "\u00c2": (0x83, "S PA S PA AH1 PA AH1 PA Z PA AH1 PA"),
        "\u00e3": (0x84, "S PA S PA AH1 PA AH1 PA N PA Z PA AH1 PA"),
        "\u00c3": (0x8E, "S PA S PA AH1 PA AH1 PA N PA Z PA AH1 PA"),
        "\u00e0": (0x85, "S PA S PA AH1 PA AH1 PA Z PA AH1 PA"),
        "\u00c0": (0x85, "S PA S PA AH1 PA AH1 PA Z PA AH1 PA"),
        "\u00e7": (0x87, "S PA S PA AH1 PA S PA Z PA AH1 PA"),
        "\u00c7": (0x80, "S PA S PA AH1 PA S PA Z PA AH1 PA"),
        "\u00e9": (0x82, "S PA S PA AH1 PA E1 PA Z PA AH1 PA"),
        "\u00c9": (0x90, "S PA S PA AH1 PA E1 PA Z PA AH1 PA"),
        "\u00ea": (0x88, "S PA S PA AH1 PA E1 PA Z PA AH1 PA"),
        "\u00ca": (0x88, "S PA S PA AH1 PA E1 PA Z PA AH1 PA"),
        "\u00ed": (0xA1, "S PA S PA AH1 PA Y PA Z PA AH1 PA"),
        "\u00cd": (0xA1, "S PA S PA AH1 PA Y PA Z PA AH1 PA"),
        "\u00f3": (0xA2, "S PA S PA AH1 PA O PA Z PA AH1 PA"),
        "\u00d3": (0xA2, "S PA S PA AH1 PA O PA Z PA AH1 PA"),
        "\u00f5": (0x94, "S PA S PA AH1 PA O PA Z PA AH1 PA"),
        "\u00d5": (0x99, "S PA S PA AH1 PA O PA Z PA AH1 PA"),
        "\u00fa": (0xA3, "S PA S PA AH1 PA U1 PA Z PA AH1 PA"),
        "\u00da": (0xA3, "S PA S PA AH1 PA U1 PA Z PA AH1 PA"),
        "\u00f4": (None, None),
        "\u00d4": (None, None),
    }),
    "bl2_pt_br_1998_12": (16, 4, "sa{}sa", {
        "\u00e1": (0xA0, "Z PA AH1 PA AH1 PA Z PA AH1 PA"),
        "\u00c1": (0xA0, "Z PA AH1 PA AH1 PA Z PA AH1 PA"),
        "\u00e2": (0x83, "Z PA AH1 PA AH1 PA Z PA AH1 PA"),
        "\u00c2": (0x83, "Z PA AH1 PA AH1 PA Z PA AH1 PA"),
        "\u00e3": (0x84, "Z PA AH1 PA UH3 PA"),
        "\u00c3": (0x8E, "Z PA AH1 PA UH3 PA"),
        "\u00e0": (0x85, "Z PA AH1 PA AH1 PA Z PA AH1 PA"),
        "\u00c0": (0x85, "Z PA AH1 PA AH1 PA Z PA AH1 PA"),
        "\u00e7": (0x87, "Z PA AH1 PA S PA Z PA AH1 PA"),
        "\u00c7": (0x80, "Z PA AH1 PA S PA Z PA AH1 PA"),
        "\u00e9": (0x82, "Z PA AH1 PA E1 PA Z PA AH1 PA"),
        "\u00c9": (0x90, "Z PA AH1 PA E1 PA Z PA AH1 PA"),
        "\u00ea": (0x88, "Z PA AH1 PA E1 PA Z PA AH1 PA"),
        "\u00ca": (0x88, "Z PA AH1 PA E1 PA Z PA AH1 PA"),
        "\u00ed": (0xA1, "Z PA AH1 PA Y PA Z PA AH1 PA"),
        "\u00cd": (0xA1, "Z PA AH1 PA Y PA Z PA AH1 PA"),
        "\u00f3": (0xA2, "Z PA AH1 PA O PA Z PA AH1 PA"),
        "\u00d3": (0xA2, "Z PA AH1 PA O PA Z PA AH1 PA"),
        "\u00f5": (0x94, "Z PA AH1 PA O PA Z PA AH1 PA"),
        "\u00d5": (0x99, "Z PA AH1 PA O PA Z PA AH1 PA"),
        "\u00fa": (0xA3, "Z PA AH1 PA U1 PA Z PA AH1 PA"),
        "\u00da": (0xA3, "Z PA AH1 PA U1 PA Z PA AH1 PA"),
        "\u00f4": (None, None),
        "\u00d4": (None, None),
    }),
    "bl2_ru_1998_12": (17, 5, "sa{}sa", {
        "\u0430": (0xA0, "S PA AH PA AH PA S PA AH PA"),
        "\u0410": (0x80, "S PA AH PA AH PA S PA AH PA"),
        "\u0431": (0xA1, "S PA AH PA B PA S PA AH PA"),
        "\u0411": (0x81, "S PA AH PA B PA S PA AH PA"),
        "\u0432": (0xA2, "S PA AH PA V PA S PA AH PA"),
        "\u0412": (0x82, "S PA AH PA V PA S PA AH PA"),
        "\u0433": (0xA3, "S PA AH PA K PA HVC PA S PA AH PA"),
        "\u0413": (0x83, "S PA AH PA K PA HVC PA S PA AH PA"),
        "\u0434": (0xA4, "S PA AH PA D PA S PA AH PA"),
        "\u0414": (0x84, "S PA AH PA D PA S PA AH PA"),
        "\u0435": (0xA5, "S PA AH PA Y1 PA EH PA S PA AH PA"),
        "\u0415": (0x85, "S PA AH PA Y1 PA EH PA S PA AH PA"),
        "\u0451": (0xF1, "S PA AH PA Y1 PA OU PA OU PA S PA AH PA"),
        "\u0401": (0xF0, "S PA AH PA Y1 PA OU PA OU PA S PA AH PA"),
        "\u0436": (0xA6, "S PA AH PA J PA S PA AH PA"),
        "\u0416": (0x86, "S PA AH PA J PA S PA AH PA"),
        "\u0437": (0xA7, "S PA AH PA Z PA S PA AH PA"),
        "\u0417": (0x87, "S PA AH PA Z PA S PA AH PA"),
        "\u0438": (0xA8, "S PA AH PA E PA E PA S PA AH PA"),
        "\u0418": (0x88, "S PA AH PA E PA E PA S PA AH PA"),
        "\u0439": (0xA9, "S PA AH PA Y1 PA S PA AH PA"),
        "\u0419": (0x89, "S PA AH PA Y1 PA S PA AH PA"),
        "\u043a": (0xAA, "S PA AH PA K PA S PA AH PA"),
        "\u041a": (0x8A, "S PA AH PA K PA S PA AH PA"),
        "\u043b": (0xAB, "S PA AH PA L PA S PA AH PA"),
        "\u041b": (0x8B, "S PA AH PA L PA S PA AH PA"),
        "\u043c": (0xAC, "S PA AH PA M PA S PA AH PA"),
        "\u041c": (0x8C, "S PA AH PA M PA S PA AH PA"),
        "\u043d": (0xAD, "S PA AH PA N PA S PA AH PA"),
        "\u041d": (0x8D, "S PA AH PA N PA S PA AH PA"),
        "\u043e": (0xAE, "S PA AH PA O PA S PA AH PA"),
        "\u041e": (0x8E, "S PA AH PA O PA S PA AH PA"),
        "\u043f": (0xAF, "S PA AH PA P PA S PA AH PA"),
        "\u041f": (0x8F, "S PA AH PA P PA S PA AH PA"),
        "\u0440": (0xE0, "S PA AH PA R PA K PA R PA S PA AH PA"),
        "\u0420": (0x90, "S PA AH PA R PA K PA R PA S PA AH PA"),
        "\u0441": (0xE1, "S PA AH PA S PA S PA AH PA"),
        "\u0421": (0x91, "S PA AH PA S PA S PA AH PA"),
        "\u0442": (0xE2, "S PA AH PA T PA S PA AH PA"),
        "\u0422": (0x92, "S PA AH PA T PA S PA AH PA"),
        "\u0443": (0xE3, "S PA AH PA U1 PA U1 PA S PA AH PA"),
        "\u0423": (0xE3, "S PA AH PA U1 PA U1 PA S PA AH PA"),
        "\u0444": (0xE4, "S PA AH PA F PA S PA AH PA"),
        "\u0424": (0x94, "S PA AH PA F PA S PA AH PA"),
        "\u0445": (0xE5, "S PA AH PA OU PA HF PA S PA AH PA"),
        "\u0425": (0x95, "S PA AH PA OU PA HF PA S PA AH PA"),
        "\u0446": (0xE6, "S PA AH PA T PA S PA S PA AH PA"),
        "\u0426": (0x96, "S PA AH PA T PA S PA S PA AH PA"),
        "\u0447": (0xE7, "S PA AH PA T PA SCH PA S PA AH PA"),
        "\u0427": (0x97, "S PA AH PA T PA SCH PA S PA AH PA"),
        "\u0448": (0xE8, "S PA AH PA SCH PA S PA AH PA"),
        "\u0428": (0x98, "S PA AH PA SCH PA S PA AH PA"),
        "\u0449": (0xE9, "S PA AH PA SCH PA SCH PA SCH PA I PA S PA AH PA"),
        "\u0429": (0x99, "S PA AH PA SCH PA SCH PA SCH PA I PA S PA AH PA"),
        "\u044a": (0xEA, "S PA AH PA Y1 PA S PA AH PA"),
        "\u042a": (0x9A, "S PA AH PA Y1 PA S PA AH PA"),
        "\u044b": (0xEB, "S PA AH PA I PA S PA AH PA"),
        "\u042b": (0x9B, "S PA AH PA I PA S PA AH PA"),
        "\u044c": (0xEC, "S PA AH PA Y1 PA S PA AH PA"),
        "\u042c": (0x9C, "S PA AH PA Y1 PA S PA AH PA"),
        "\u044d": (0xED, "S PA AH PA EH PA S PA AH PA"),
        "\u042d": (0x9D, "S PA AH PA EH PA S PA AH PA"),
        "\u044e": (0xEE, "S PA AH PA Y1 PA U PA S PA AH PA"),
        "\u042e": (0x9E, "S PA AH PA Y1 PA U PA S PA AH PA"),
        "\u044f": (0xEF, "S PA AH PA Y1 PA AH PA S PA AH PA"),
        "\u042f": (0x9F, "S PA AH PA Y1 PA AH PA S PA AH PA"),
    }),
    # the Arabic (UAE) unit: code page 864, the 27 letters it speaks (isolated or initial forms), every Arabic
    # letter's forms sent as the one it speaks (gen_cp864ar.py FOLDS); a letter it has no byte for (alef maksura,
    # teh marbuta, zah) stays the gap the unit has, never sent as another letter (Tomi).  The phonemes are its own for
    # each byte, read from the sweep (every byte 80h-FFh between two x's, 2026-10-16).  Before: plain letters (its
    # text column was -), which drop every Arabic one.
    "bl2_ar_ae_1998_12": (18, 0, "x{}x.", {
        "\u0622": (0xC7, "K PA S PA AE PA K PA S PA"),   # LETTER ALEF WITH MADDA ABOVE
        "\u0623": (0xC7, "K PA S PA AE PA K PA S PA"),   # LETTER ALEF WITH HAMZA ABOVE
        "\u0624": (0xE8, "K PA S PA W PA K PA S PA"),   # LETTER WAW WITH HAMZA ABOVE
        "\u0625": (0xC7, "K PA S PA AE PA K PA S PA"),   # LETTER ALEF WITH HAMZA BELOW
        "\u0626": (0xFD, "K PA S PA Y1 PA K PA S PA"),   # LETTER YEH WITH HAMZA ABOVE
        "\u0627": (0xC7, "K PA S PA AE PA K PA S PA"),   # LETTER ALEF
        "\u0628": (0xA9, "K PA S PA B PA K PA S PA"),   # LETTER BEH
        "\u062A": (0xAA, "K PA S PA T PA K PA S PA"),   # LETTER TEH
        "\u062B": (0xAB, "K PA S PA T PA K PA S PA"),   # LETTER THEH
        "\u062C": (0xAD, "K PA S PA J PA K PA S PA"),   # LETTER JEEM
        "\u062D": (0xAE, "K PA S PA OU PA HF PA K PA S PA"),   # LETTER HAH
        "\u062E": (0xAF, "K PA S PA K PA K PA S PA"),   # LETTER KHAH
        "\u062F": (0xCF, "K PA S PA D PA K PA S PA"),   # LETTER DAL
        "\u0630": (0xD0, "K PA S PA D PA K PA S PA"),   # LETTER THAL
        "\u0631": (0xD1, "K PA S PA R1 PA K PA S PA"),   # LETTER REH
        "\u0632": (0xD2, "K PA S PA Z PA K PA S PA"),   # LETTER ZAIN
        "\u0633": (0xD3, "K PA S PA S PA K PA S PA"),   # LETTER SEEN
        "\u0634": (0xD4, "K PA S PA SCH PA K PA S PA"),   # LETTER SHEEN
        "\u0635": (0xD5, "K PA S PA S PA S PA K PA S PA"),   # LETTER SAD
        "\u0636": (0xD6, "K PA S PA D PA D PA K PA S PA"),   # LETTER DAD
        "\u0637": (0xD7, "K PA S PA T PA T PA K PA S PA"),   # LETTER TAH
        "\u0639": (0xDF, "K PA S PA K PA HVC PA K PA S PA"),   # LETTER AIN
        "\u063A": (0xEE, "K PA S PA T PA SCH PA K PA S PA"),   # LETTER GHAIN
        "\u0641": (0xE1, "K PA S PA F PA K PA S PA"),   # LETTER FEH
        "\u0642": (0xE2, "K PA S PA K PA K PA S PA"),   # LETTER QAF
        "\u0643": (0xFC, "K PA S PA K PA K PA S PA"),   # LETTER KAF
        "\u0644": (0xFB, "K PA S PA L PA K PA S PA"),   # LETTER LAM
        "\u0645": (0xEF, "K PA S PA M PA K PA S PA"),   # LETTER MEEM
        "\u0646": (0xF2, "K PA S PA N PA K PA S PA"),   # LETTER NOON
        "\u0647": (0xF3, "K PA S PA OU PA HF PA K PA S PA"),   # LETTER HEH
        "\u0648": (0xE8, "K PA S PA W PA K PA S PA"),   # LETTER WAW
        "\u064A": (0xFD, "K PA S PA Y1 PA K PA S PA"),   # LETTER YEH
        "\uFE91": (0xA9, "K PA S PA B PA K PA S PA"),   # LETTER BEH INITIAL FORM
        "\uFEE8": (0xF2, "K PA S PA N PA K PA S PA"),   # LETTER NOON MEDIAL FORM
        "\uFEEA": (0xF3, "K PA S PA OU PA HF PA K PA S PA"),   # LETTER HEH FINAL FORM
    }),
}
# whole words, end to end: the bytes the unit gets (the vowel marks, tatweel and a bare hamza dropped inside the word,
# not made spaces; Arabic-Indic digits as ASCII)
WORDS = {"bl2_ar_ae_1998_12": [
    ("\u0645\u064E\u0631\u0652\u062D\u064E\u0628\u064B\u0627", b"\xef\xd1\xae\xa9\xc7"),     # marhaban, with its marks
    ("\u0645\u062F\u0631\u0633\u0629 \u0661\u0662\u0663", b"\xef\xcf\xd1\xd3 123"),         # madrasa 123: no teh marbuta
    ("\u0633\u0640\u0644\u0627\u0645", b"\xd3\xfb\xc7\xef"),                                # salam, with a tatweel
    ("\u0633\u0645\u0627\u0621", b"\xd3\xef\xc7"),                                          # sama', its hamza dropped
]}


def base(letter, want=None):
    """The letter without its accent: what translit.h sends for a letter the unit has no byte for -- or the plain
    letter a fold sends ("=i": the Turkish dotted I goes out as i)."""
    if want and want.startswith("="):
        return want[1:]
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


_lib = None


def worker_init(lib_path, chip_path):
    global _lib
    _lib = load(lib_path, chip_path)


def speak_letters(job):
    """In a worker: one release's voice, each letter in its frame -> [(ok, line)]."""
    rid, k, fw, enc, frame, letters, tmp = job
    lib, out = _lib, []
    st = os.path.join(tmp, "%s.state" % rid)
    err = ctypes.create_string_buffer(300)
    if not lib.blv_make_release_state(fw.encode(), k, st.encode(), test_releases.PROGRESS(0), None, err, 300):
        return [(False, "state   %s: %s" % (rid, err.value.decode(errors="replace")))]
    v = lib.blv_create(fw.encode(), st.encode(), enc, float(RATE), 1, 0, err, 300)
    if not v:
        return [(False, "voice   %s: %s" % (rid, err.value.decode(errors="replace")))]
    h = lib.blv_host(v)
    for letter, (byte, want) in letters.items():
        if byte is None:                         # said as its base letter (and so not skipped)
            want = phonemes(lib, v, h, frame.format(base(letter, want)))
        got = phonemes(lib, v, h, frame.format(letter))
        out.append((got == want, "letter  %s U+%04X: %s%s" % (rid, ord(letter), got, "" if got == want else
                                                               " (want %s)" % want)))
    lib.blv_destroy(v)
    os.remove(st)
    return out


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
    jobs = []
    for rid, (want_text, before, frame, letters) in RELEASES.items():
        k = next(i for i, r in enumerate(table) if r["id"] == rid)
        text = test_releases.TEXT_ID[table[k]["text"]]
        report(text == want_text, "row     %s's text encoding is %d: %d" % (rid, want_text, text))
        enc = before if BREAK else text
        for letter, (byte, expect) in letters.items():
            n = lib.blv_say_bytes(frame.format(letter).encode("utf-8"), enc, 0, buf, 256)
            got = buf.raw[:n].split(b"\r")[0]
            want = frame.format("\x00").encode().replace(b"\x00", base(letter, expect).encode() if byte is None
                                                         else bytes([byte]))
            report(got == want, "bytes   %s U+%04X -> %r (want %r)" % (rid, ord(letter), got, want))
        for word, want in WORDS.get(rid, ()):
            n = lib.blv_say_bytes(word.encode("utf-8"), enc, 0, buf, 256)
            got = buf.raw[:n].split(b"\r")[0]
            report(got == want, "word    %s %a -> %r (want %r)" % (rid, word, got, want))
        if k not in found:
            print("skip %s: its firmware is not in the firmware folder" % rid)
            continue
        jobs.append((rid, k, found[k], enc, frame, letters, tmp))
    # one voice per release, in parallel (each boots its own unit)
    with ProcessPoolExecutor(max_workers=max(1, min(len(jobs), (os.cpu_count() or 2) // 2)), initializer=worker_init,
                             initargs=(a.lib, a.chip)) as ex:
        for lines in ex.map(speak_letters, jobs):
            for ok, what in lines:
                report(ok, what)
    os.rmdir(tmp)
    print("unit letters: every check passed" if not bad else "unit letters: %d FAILED" % bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

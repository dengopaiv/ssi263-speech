/* bl_cphun.h -- the Hungarian Braille Lite 2000's letters (BL2HUN.BNS, the July 1999 release): the byte the voice
 * sends for each accented letter, as its speech rules say it.
 *
 * Not a Python codec, so not from gen_cp850.py: read from the unit itself.  Every byte 80h-FFh was sent to the
 * emulated unit in speech-box mode inside "b_t" and "ter_", and the phonemes it said logged (2026-10-15).  These
 * seventeen bytes are the ones it speaks (the nine accented vowels, both cases, o double acute's two on one byte);
 * every other byte there says nothing.  They are the CWI-2 code page's letters, with two differences in what the
 * rules accept:
 *   - o double acute: only its capital's byte (A7h) is spoken.  The lower case one's (93h), which the unit's own text
 *     uses, says nothing, so the voice sends both cases as A7h (bl_hun_fold).
 *   - I acute is 8Ch.
 * A long vowel comes out as its phoneme three times (a acute AE1 AE1 AE1); that is the unit's rule, not ours.
 */
#ifndef BL_CPHUN_H
#define BL_CPHUN_H

/* the code point of each byte 0x80 + i (0: the unit says nothing for it) */
static const unsigned short bl_cphun_high[128] = {
    0x0000, 0x00FC, 0x00E9, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,     /* 81 u diaeresis, 82 e acute */
    0x0000, 0x0000, 0x0000, 0x0000, 0x00CD, 0x0000, 0x0000, 0x00C1,     /* 8C I acute, 8F A acute */
    0x00C9, 0x0000, 0x0000, 0x0000, 0x00F6, 0x00D3, 0x0171, 0x00DA,     /* 90 E, 94 o diaeresis, 95 O, 96 u dbl, 97 U */
    0x0170, 0x00D6, 0x00DC, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,     /* 98 U double acute, 99 O, 9A U diaeresis */
    0x00E1, 0x00ED, 0x00F3, 0x00FA, 0x0000, 0x0000, 0x0000, 0x0150,     /* A0-A3 a i o u acute, A7 O double acute */
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
    0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000, 0x0000,
};

/* o double acute is sent as its capital (the unit speaks no other byte for it) */
static unsigned bl_hun_fold(unsigned c)
{
    return c == 0x0151 ? 0x0150 : c;
}

#endif

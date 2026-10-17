/* test_unit_native.c -- the Braille Lite unit screen's native part (../app/src/main/cpp/ssa_unit.c) on real firmware:
 *
 *   test_unit_native FIRMWARE_DIR SCRATCH_DIR
 *
 *   - the list: only units whose firmware is there;
 *   - keys: a unit keyed through ssa_unit_key (F D S J K L, the space bar, ; as keys going down and up) sounds the
 *     same, sample for sample, as the same unit keyed directly through emu_unit.h the way UnitRunner.swift does
 *     (emu_keys_down with the bits held, emu_key with the chord when the last key comes up), the bits written out
 *     here by hand; a chord is answered; a key that is not the unit's is left to the screen;
 *   - the Type 'n Speak (when tns/TNSENG.TNS is there): its keys as its own key events, down and up, Shift a key of
 *     its own, against emu_key with tns_keys.h's codes written out by hand;
 *   - its memory saved, the unit switched on again from it;
 *   - a release unit (the first one the folder has), its first state made by its own recipe.
 *
 * SSI263_UNIT_TEST_BREAK=1 swaps dots 1 and 4 in ssa_unit (ssa_unit_break): the keys' check must fail.
 */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ssa_unit.h"
#include "emu_unit.h"
#include "keys.h"

#define RATE 22050
#define BLOCK 441                       /* 20 ms */

static int failures;

static void check(const char *name, int ok, const char *detail)
{
    printf("%-4s %-40s %s\n", ok ? "ok" : "FAIL", name, detail);
    failures += !ok;
}

static double rms(const short *p, int n)
{
    double s = 0;
    int i;
    for (i = 0; i < n; i++)
        s += (double)p[i] * p[i];
    return n ? sqrt(s / n) / 32768.0 : 0.0;
}

/* a scripted key: at block `at`, key goes down or up; the direct unit's bits held after it and its chord (0: none) */
typedef struct { int at, key, down, held, chord; } step;

static const step BL_KEYS[] = {
    {400, 'f', 1, 0x01, 0}, {402, 'd', 1, 0x03, 0}, {407, 'f', 0, 0x02, 0}, {410, 'd', 0, 0x00, 0x03},   /* b */
    {600, ' ', 1, 0x40, 0}, {602, 'k', 1, 0x50, 0}, {606, ' ', 0, 0x10, 0}, {608, 'k', 0, 0x00, 0x50},
    {700, 'j', 1, 0x08, 0}, {701, 'l', 1, 0x28, 0}, {703, 's', 1, 0x2C, 0}, {706, 'j', 0, 0x24, 0},
    {707, 'l', 0, 0x04, 0}, {709, 's', 0, 0x00, 0x2C},
    {800, ';', 1, 0x80, 0}, {815, ';', 0, 0x00, 0x80},                                              /* the bar */
};
#define N_BL (int)(sizeof BL_KEYS / sizeof BL_KEYS[0])

/* the Type 'n Speak: h, then Shift + a (tns_keys.h: h C8h, a 94h, left Shift E1h; up = the code without bit 7) */
static const step TNS_KEYS[] = {
    {400, 'h', 1, 0, 0xC8}, {405, 'h', 0, 0, 0x48},
    {500, K_LSHIFT, 1, 0, 0xE1}, {503, 'a', 1, 0, 0x94}, {508, 'a', 0, 0, 0x14}, {512, K_LSHIFT, 0, 0, 0x61},
};
#define N_TNS (int)(sizeof TNS_KEYS / sizeof TNS_KEYS[0])

/* the unit through ssa_unit and the same through emu_unit directly, keyed by the script, `blocks` 20-ms blocks: 1
   when every sample is the same; a and b get the sound */
static int keyed_alike(const char *dir, const char *key, const char *saved_dir, const step *keys, int n_keys, int tns,
                       int blocks, short *a, short *b, char *d, int dlen)
{
    char err[300];
    ssa_unit *u = ssa_unit_start(dir, key, saved_dir, RATE, 0, NULL, NULL, err, sizeof err);
    emc_unit units[EMC_MAX];
    emu_unit *e = NULL;
    int n = ssa_unit_list(dir, units, EMC_MAX), i, k = 0, same, first = -1;
    if (!u) {
        snprintf(d, (size_t)dlen, "ssa_unit_start: %s", err);
        return 0;
    }
    for (i = 0; i < n; i++)
        if (!strcmp(units[i].key, key))
            e = emu_create(units[i].kind, units[i].firmware, units[i].factory[0] ? units[i].factory : NULL, RATE, 0,
                           err, sizeof err);
    if (!e) {
        snprintf(d, (size_t)dlen, "emu_create: %s", err);
        ssa_unit_stop(u);
        return 0;
    }
    emu_set_idle(e, 0, 1, 1, 1);
    for (i = 0; i < blocks; i++) {
        for (; k < n_keys && keys[k].at == i; k++) {
            ssa_unit_key(u, keys[k].key, keys[k].down);
            if (tns)
                emu_key(e, keys[k].chord);
            else {
                emu_keys_down(e, keys[k].held);
                if (keys[k].chord)
                    emu_key(e, keys[k].chord);
            }
        }
        ssa_unit_render(u, a + (long)i * BLOCK, BLOCK);
        emu_render(e, b + (long)i * BLOCK, BLOCK);
    }
    same = memcmp(a, b, (size_t)blocks * BLOCK * sizeof *a) == 0;
    for (i = 0; !same && i < blocks * BLOCK && first < 0; i++)
        if (a[i] != b[i])
            first = i;
    snprintf(d, (size_t)dlen, "%s over %d s%s", same ? "every sample the same" : "differ", blocks / 50,
             same ? "" : "");
    if (!same)
        snprintf(d + strlen(d), (size_t)(dlen - (int)strlen(d)), " from %.2f s", (double)first / RATE);
    emu_destroy(e);
    ssa_unit_stop(u);
    return same;
}

int main(int argc, char **argv)
{
    const char *dir, *scratch, *brk = getenv("SSI263_UNIT_TEST_BREAK");
    emc_unit units[EMC_MAX];
    char d[400], saved_dir[1024], err[300];
    int n, i, all_present = 1, blocks = 1000;
    short *a, *b;
    if (argc != 3) {
        fprintf(stderr, "usage: test_unit_native FIRMWARE_DIR SCRATCH_DIR\n");
        return 2;
    }
    dir = argv[1];
    scratch = argv[2];
    ssa_unit_break = brk ? atoi(brk) : 0;
    a = (short *)malloc((size_t)blocks * BLOCK * sizeof *a);
    b = (short *)malloc((size_t)blocks * BLOCK * sizeof *b);
    if (!a || !b)
        return 1;

    n = ssa_unit_list(dir, units, EMC_MAX);
    for (i = 0; i < n; i++)
        all_present &= units[i].present;
    snprintf(d, sizeof d, "%d units, the first %s", n, n ? units[0].name : "-");
    check("the list: only units with their firmware", n > 0 && all_present, d);

    snprintf(saved_dir, sizeof saved_dir, "%s/keys", scratch);
    {
        int ok = keyed_alike(dir, "bl-en", saved_dir, BL_KEYS, N_BL, 0, blocks, a, b, d, sizeof d);
        check("keys: the chords the unit gets", ok, d);
        snprintf(d, sizeof d, "rms %.4f over 8.2-10 s, %.4f over 7-8 s", rms(a + 410 * BLOCK, 90 * BLOCK),
                 rms(a + 350 * BLOCK, 50 * BLOCK));
        check("keys: a chord is answered", rms(a + 410 * BLOCK, 90 * BLOCK) > 3 * rms(a + 350 * BLOCK, 50 * BLOCK)
                                           && rms(a + 410 * BLOCK, 90 * BLOCK) > 0.002, d);
    }
    {   /* a key that is not the unit's is the screen's (Tab moves focus, Back leaves) */
        ssa_unit *u = ssa_unit_start(dir, "bl-en", saved_dir, RATE, 0, NULL, NULL, err, sizeof err);
        int tab = u ? ssa_unit_key(u, K_TAB, 1) : -1, x = u ? ssa_unit_key(u, 'x', 1) : -1;
        snprintf(d, sizeof d, "Tab %s, x %s", tab ? "taken" : "left", x ? "taken" : "left");
        check("keys: the others left to the screen", tab == 0 && x == 0, d);

        /* its memory saved and the unit started again from it */
        ssa_unit_render(u, a, 6 * RATE / BLOCK * BLOCK);
        snprintf(d, sizeof d, "saved: %s", ssa_unit_stop(u) ? "yes" : "no");
        u = ssa_unit_start(dir, "bl-en", saved_dir, RATE, 0, NULL, NULL, err, sizeof err);
        if (u)
            ssa_unit_render(u, a, 6 * RATE);
        snprintf(d + strlen(d), sizeof d - strlen(d), "; started from it: %s, rms %.4f over 6 s", u ? "yes" : err,
                 u ? rms(a, 6 * RATE) : 0.0);
        check("its memory saved and started again", u && rms(a, 6 * RATE) > 0.005, d);
        ssa_unit_stop(u);
    }

    for (i = 0; i < n && strcmp(units[i].key, "tns-en"); i++)
        ;
    if (i < n) {
        snprintf(saved_dir, sizeof saved_dir, "%s/tns", scratch);
        check("Type 'n Speak: its keys down and up",
              keyed_alike(dir, "tns-en", saved_dir, TNS_KEYS, N_TNS, 1, 700, a, b, d, sizeof d), d);
        snprintf(d, sizeof d, "rms %.4f over 8.1-12 s, %.4f over 7-8 s", rms(a + 405 * BLOCK, 195 * BLOCK),
                 rms(a + 350 * BLOCK, 50 * BLOCK));
        check("Type 'n Speak: its keys answered", rms(a + 405 * BLOCK, 195 * BLOCK) > 3 * rms(a + 350 * BLOCK,
                                                                                            50 * BLOCK), d);
    } else
        printf("skip Type 'n Speak: no tns/TNSENG.TNS in %s\n", dir);

    for (i = 0; i < n && units[i].release < 0; i++)
        ;
    for (; i < n && !emc_needs_factory(&units[i]); i++)
        ;
    if (i < n) {
        ssa_unit *u;
        snprintf(saved_dir, sizeof saved_dir, "%s/release", scratch);
        u = ssa_unit_start(dir, units[i].key, saved_dir, RATE, 0, NULL, NULL, err, sizeof err);
        if (u)
            ssa_unit_render(u, a, 6 * RATE);
        snprintf(d, sizeof d, "%s: %s, rms %.4f over 6 s", units[i].key, u ? "its state made, started" : err,
                 u ? rms(a, 6 * RATE) : 0.0);
        check("a release unit's first start", u && rms(a, 6 * RATE) > 0.005, d);
        ssa_unit_stop(u);
    } else
        printf("skip a release unit: none in %s\n", dir);

    free(a);
    free(b);
    printf("%s\n", failures ? "unit: FAILED" : "unit: all passed");
    return failures ? 1 : 0;
}

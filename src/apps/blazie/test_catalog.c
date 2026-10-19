/* test_catalog.c -- the emulator catalog (emu_catalog.h), headless.
 *
 *   test_catalog FIRMWARE_DIR
 *   test_catalog FIRMWARE_DIR --list    every unit the shells' menus would offer from FIRMWARE_DIR, one per line:
 *                                       "unit <key> <present 0|1> <name>" (the packagers' check of what a download's
 *                                       firmware folder brings: the Braille 'n Speak 640s in firmware/bns640/)
 *
 * 1. The eight units the emulators always had keep their names, keys, saved-state names and settings values (users'
 *    data), in their order, read from FIRMWARE_DIR as the shells do.
 * 2. No firmware, no unit (Tomi): in a folder of its own holding only two release .BNS files (Hungarian, Turkish, one
 *    folder down), the catalog lists the eight old units, none present (the four a menu always shows marked so), and
 *    exactly those two release units; with one file taken away, only the other.
 * 3. A release unit needs its factory state made, an old unit never; the Hungarian one made = its release's hash.
 * Control: CATALOG_BREAK=1 (emc_catalog_break) lists a release unit without its firmware; part 2 must fail.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <direct.h>
#include <process.h>
#define MKDIR(p) _mkdir(p)
#define getpid _getpid
#else
#include <sys/stat.h>
#include <unistd.h>
#define MKDIR(p) mkdir(p, 0755)
#endif

#include "emu_catalog.h"
#include "emu_unit.h"

static int bad = 0;

static void result(int ok, const char *what, const char *detail)
{
    printf("%-4s %s%s%s\n", ok ? "ok" : "FAIL", what, detail && *detail ? ": " : "", detail ? detail : "");
    bad += !ok;
}

static int copy(const char *from, const char *to)
{
    FILE *a = fopen(from, "rb"), *b;
    char buf[65536];
    size_t n;
    int ok = 1;
    if (!a)
        return 0;
    b = fopen(to, "wb");
    if (!b) {
        fclose(a);
        return 0;
    }
    while ((n = fread(buf, 1, sizeof buf, a)) > 0)
        ok &= fwrite(buf, 1, n, b) == n;
    fclose(a);
    return fclose(b) == 0 && ok;
}

int main(int argc, char **argv)
{
    static const char *const WANT[8][4] = {
        {"Braille Lite 2000 (English)", "bl-en", "english.state", "english"},
        {"Braille Lite 2000 (Spanish)", "bl-es", "spanish.state", "spanish"},
        {"Type 'n Speak (English)", "tns-en", "tns_english.state", "tns_english"},
        {"Type 'n Speak (Spanish)", "tns-es", "tns_spanish.state", "tns_spanish"},
        {"Braille 'n Speak 2000 (English)", "bns-en", "bns_english.state", "bns_english"},
        {"Braille 'n Speak 2000 (Slovak)", "bns-sk", "bns_slovak.state", "bns_slovak"},
        {"Braille Lite 2000 (German)", "bl-de", "german.state", "german"},
        {"Braille Lite 2000 (Italian)", "bl-it", "italian.state", "italian"},
    };
    static emc_unit u[EMC_MAX];
    char tmp[EMC_PATH], sub[EMC_PATH], hun[EMC_PATH], tur[EMC_PATH], src[EMC_PATH], st[EMC_PATH], err[300], d[600];
    int n, i, k, old = 0, ok;
    if (argc == 3 && !strcmp(argv[2], "--list")) {
        n = emc_list(argv[1], u, EMC_MAX);
        for (i = 0; i < n; i++)
            printf("unit %s %d %s\n", u[i].key, u[i].present, u[i].name);
        return 0;
    }
    if (argc != 2) {
        fprintf(stderr, "usage: test_catalog FIRMWARE_DIR [--list]\n");
        return 2;
    }
    emc_catalog_break = getenv("CATALOG_BREAK") != NULL;

    /* 1. the old units, as the shells list them from the firmware folder */
    n = emc_list(argv[1], u, EMC_MAX);
    for (i = 0, k = 0; i < n && k < 8; i++) {
        if (u[i].release >= 0)
            break;
        while (k < 8 && strcmp(u[i].key, WANT[k][1]))
            k++;                            /* one not present here is left out of the list */
        if (k < 8 && !strcmp(u[i].name, WANT[k][0]) && !strcmp(u[i].saved, WANT[k][2]) &&
            !strcmp(u[i].ini, WANT[k][3]))
            old++;
        else {
            snprintf(d, sizeof d, "%s: %s / %s / %s", u[i].key, u[i].name, u[i].saved, u[i].ini);
            result(0, "an old unit changed", d);
        }
    }
    snprintf(d, sizeof d, "%d of 8, each with its name, key, saved-state name and settings value, in order", old);
    result(old == 8 && u[0].always && u[3].always && !u[4].always, "the old units as before", d);

    /* 2. no firmware, no unit */
    snprintf(src, sizeof src, "%s/bl2000/BL2HUN.BNS", argv[1]);
    snprintf(st, sizeof st, "%s/bl2000/BL2TUR.BNS", argv[1]);
    {
        FILE *f = fopen(src, "rb"), *g = fopen(st, "rb");
        if (f) fclose(f);
        if (g) fclose(g);
        if (!f || !g) {
            printf("skip the release units: bl2000/BL2HUN.BNS and BL2TUR.BNS are not in %s\n", argv[1]);
            printf(bad ? "catalog: %d FAILED\n" : "catalog: every case as expected\n", bad);
            return bad != 0;
        }
    }
    snprintf(tmp, sizeof tmp, "catalog-test-%ld.tmp", (long)getpid());   /* its own: the control runs alongside */
    snprintf(sub, sizeof sub, "%s/some folder", tmp);
    MKDIR(tmp);
    MKDIR(sub);
    snprintf(hun, sizeof hun, "%s/BL2HUN.BNS", sub);
    snprintf(tur, sizeof tur, "%s/bl2tur.bns", sub);    /* the suffix in any case */
    if (!copy(src, hun) || !copy(st, tur)) {
        result(0, "copy the two firmware files", tmp);
        return 1;
    }
    n = emc_list(tmp, u, EMC_MAX);
    {
        int always = 0, absent = 0, rel = 0, h = -1, t = -1;
        for (i = 0; i < n; i++) {
            always += u[i].release < 0 && u[i].always;
            absent += u[i].release < 0 && !u[i].present;
            if (u[i].release >= 0) {
                rel++;
                if (!strcmp(u[i].key, "bl2_hu_1999_07") && !strcmp(u[i].firmware, hun)) h = i;
                if (!strcmp(u[i].key, "bl2_tr_1998_12") && !strcmp(u[i].firmware, tur)) t = i;
            }
        }
        snprintf(d, sizeof d, "%d units: %d old (%d not present, %d always shown), %d release units%s%s", n, n - rel,
                 absent, always, rel, h >= 0 ? ", Hungarian" : "", t >= 0 ? ", Turkish" : "");
        result(n == 10 && absent == 8 && always == 4 && rel == 2 && h >= 0 && t >= 0,
               "a folder with two release files: those two release units, and the old eight not present", d);
        if (h >= 0) {
            snprintf(d, sizeof d, "%s, saved as %s", u[h].name, u[h].saved);
            result(!strcmp(u[h].name, "Braille Lite 2000 (Hungarian)") && !strcmp(u[h].saved,
                   "bl2_hu_1999_07.state") && !strcmp(u[h].ini, "bl2_hu_1999_07") && u[h].kind == EMU_BRAILLE_LITE,
                   "the Hungarian unit's name, saved state and settings value from the release table", d);
        }
    }
    remove(tur);
    n = emc_list(tmp, u, EMC_MAX);
    {
        int rel = 0, h = 0;
        for (i = 0; i < n; i++)
            if (u[i].release >= 0) {
                rel++;
                h |= !strcmp(u[i].key, "bl2_hu_1999_07");
            }
        snprintf(d, sizeof d, "%d release units", rel);
        result(rel == 1 && h, "the Turkish file taken away: its unit gone, Hungarian's kept", d);
    }

    /* 3. the first start's factory state */
    for (i = 0, k = -1; i < n; i++)
        if (u[i].release >= 0)
            k = i;
    ok = k >= 0 && emc_needs_factory(&u[k]) && !emc_needs_factory(&u[0]);
    result(ok, "a release unit needs its factory state made, an old unit never", "");
    if (k >= 0) {
        snprintf(st, sizeof st, "%s/%s", tmp, u[k].saved);
        ok = emc_make_factory(&u[k], st, NULL, NULL, err, sizeof err);
        result(ok, "the Hungarian unit's factory state made = its release's hash", ok ? "" : err);
        remove(st);
    }
    remove(hun);
#ifdef _WIN32
    _rmdir(sub);
    _rmdir(tmp);
#else
    rmdir(sub);
    rmdir(tmp);
#endif
    printf(bad ? "catalog: %d FAILED\n" : "catalog: every case as expected\n", bad);
    return bad != 0;
}

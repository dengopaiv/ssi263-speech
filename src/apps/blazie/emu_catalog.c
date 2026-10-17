/* emu_catalog.c -- see emu_catalog.h. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <dirent.h>
#include <sys/stat.h>
#endif

#include "emu_catalog.h"
#include "emu_unit.h"
#include "../../csrc/blazie/bl_board.h"
#include "../../csrc/blazie/bl_files_xfer.h"
#include "../../csrc/blazie/bl_firmware.h"

int emc_catalog_break = 0;

/* The eight units the emulators always had (main_win.c, main_gtk.c and main_linux.c kept a copy each): the firmware
   and factory state in their own folder, then flat beside the others (the Linux data folder, the add-on's engine
   folder); and the releases each one covers, so the table does not list them twice. */
static const struct {
    const char *name, *key, *saved, *ini;
    int kind;
    const char *firmware[2], *state[2];
    int codepage;
    const char *covers;                     /* the release table's id, or NULL */
} LEGACY[] = {
    {"Braille Lite 2000 (English)", "bl-en", "english.state", "english", EMU_BRAILLE_LITE,
     {"BL2ENG.BNS", NULL}, {"bl2_2003_warm.state", NULL}, BLX_CP850, "bl2_en_2003_06"},
    {"Braille Lite 2000 (Spanish)", "bl-es", "spanish.state", "spanish", EMU_BRAILLE_LITE,
     {"spanish/BL2SPA.BNS", "BL2SPA.BNS"}, {"spanish/bl2spa_fresh.state", "bl2spa_fresh.state"}, BLX_CP850,
     "bl2_es_2000_09"},
    {"Type 'n Speak (English)", "tns-en", "tns_english.state", "tns_english", EMU_TYPE_N_SPEAK,
     {"tns/TNSENG.TNS", "TNSENG.TNS"}, {NULL, NULL}, BLX_CP850, NULL},
    {"Type 'n Speak (Spanish)", "tns-es", "tns_spanish.state", "tns_spanish", EMU_TYPE_N_SPEAK,
     {"tns/TNSSPA.TNS", "TNSSPA.TNS"}, {NULL, NULL}, BLX_CP850, NULL},
    /* the Braille 'n Speak 2000 on the Braille Lite's board (emu_unit.h emu_model); its factory states made from the
       firmware by make_state (make_state.c) */
    {"Braille 'n Speak 2000 (English)", "bns-en", "bns_english.state", "bns_english", EMU_BRAILLE_LITE,
     {"bns2000/BS03ENG.BNS", "BS03ENG.BNS"}, {"bns2000/bs03eng_fresh.state", "bs03eng_fresh.state"}, BLX_CP850,
     NULL},
    {"Braille 'n Speak 2000 (Slovak)", "bns-sk", "bns_slovak.state", "bns_slovak", EMU_BRAILLE_LITE,
     {"bns2000/BS2SLL.BNS", "BS2SLL.BNS"}, {"bns2000/bs2sll_fresh.state", "bs2sll_fresh.state"}, BLX_CP852,
     "bns2_sk"},
    /* Blazie's September 2000 German and Italian updates (an anonymous donation) */
    {"Braille Lite 2000 (German)", "bl-de", "german.state", "german", EMU_BRAILLE_LITE,
     {"german/Lite2000.BNS", "Lite2000_de.BNS"}, {"german/lite2000_de_fresh.state", "lite2000_de_fresh.state"},
     BLX_CP850, "bl2_de_2000_09"},
    {"Braille Lite 2000 (Italian)", "bl-it", "italian.state", "italian", EMU_BRAILLE_LITE,
     {"italian/Lite2000.BNS", "Lite2000_it.BNS"}, {"italian/lite2000_it_fresh.state", "lite2000_it_fresh.state"},
     BLX_CP850, "bl2_it_2000_09"},
};
#define N_LEGACY ((int)(sizeof LEGACY / sizeof *LEGACY))
#define N_ALWAYS 4                          /* the first four: in every menu, firmware or not */
#define MAX_BNS (0x3000 + 0x40000)          /* a .BNS: the image from 3000h, 256 KB at most */

static int is_file(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (f)
        fclose(f);
    return f != NULL;
}

/* The first of the (up to two) candidates that is a file, into out; else the first, so the shell can say where it
   looked.  1 when one was found. */
static int first_of(const char *dir, const char *const cand[2], char *out, int cap)
{
    int i;
    for (i = 0; i < 2 && cand[i]; i++) {
        snprintf(out, cap, "%s/%s", dir, cand[i]);
        if (is_file(out))
            return 1;
    }
    snprintf(out, cap, "%s/%s", dir, cand[0] ? cand[0] : "");
    return 0;
}

static int covered(int release)
{
    const char *id = blv_release_id(release);
    int i;
    for (i = 0; id && i < N_LEGACY; i++)
        if (LEGACY[i].covers && !strcmp(LEGACY[i].covers, id))
            return 1;
    return 0;
}

static int has_bns_suffix(const char *name)
{
    size_t n = strlen(name);
    return n > 4 && name[n - 4] == '.' && (name[n - 3] | 0x20) == 'b' && (name[n - 2] | 0x20) == 'n' &&
           (name[n - 1] | 0x20) == 's';
}

typedef struct {
    char path[EMC_PATH];
    int release;
} found_bns;

/* Every .BNS in dir (and, with depth 1, in the folders inside it) that is a release on the table. */
static void scan(const char *dir, int depth, found_bns *out, int *n, int cap)
{
#ifdef _WIN32
    char pat[EMC_PATH];
    WIN32_FIND_DATAA fd;
    HANDLE h;
    snprintf(pat, sizeof pat, "%s/*", dir);
    h = FindFirstFileA(pat, &fd);
    if (h == INVALID_HANDLE_VALUE)
        return;
    do {
        const char *name = fd.cFileName;
        int isdir = (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0;
#else
    DIR *d = opendir(dir);
    struct dirent *e;
    if (!d)
        return;
    while ((e = readdir(d)) != NULL) {
        const char *name = e->d_name;
        struct stat sb;
        char p[EMC_PATH];
        int isdir;
        snprintf(p, sizeof p, "%s/%s", dir, name);
        isdir = stat(p, &sb) == 0 && S_ISDIR(sb.st_mode);
#endif
        char path[EMC_PATH];
        if (name[0] == '.')
            continue;
        snprintf(path, sizeof path, "%s/%s", dir, name);
        if (isdir) {
            if (depth > 0)
                scan(path, depth - 1, out, n, cap);
        } else if (has_bns_suffix(name) && *n < cap) {
            int k = blv_release_of(path), i, dup = 0;
            for (i = 0; i < *n; i++)
                dup |= out[i].release == k;
            if (k >= 0 && !dup) {
                snprintf(out[*n].path, sizeof out[*n].path, "%s", path);
                out[(*n)++].release = k;
            }
        }
#ifdef _WIN32
    } while (FindNextFileA(h, &fd));
    FindClose(h);
#else
    }
    closedir(d);
#endif
}

static int by_name(const void *a, const void *b)
{
    return strcmp(((const emc_unit *)a)->name, ((const emc_unit *)b)->name);
}

int emc_list(const char *firmware_dir, emc_unit *out, int cap)
{
    found_bns *found = (found_bns *)calloc(EMC_MAX, sizeof *found);
    int n = 0, nf = 0, i, first_release;
    for (i = 0; i < N_LEGACY && n < cap; i++) {
        emc_unit *u = &out[n];
        memset(u, 0, sizeof *u);
        u->name = LEGACY[i].name;
        u->key = LEGACY[i].key;
        u->ini = LEGACY[i].ini;
        snprintf(u->saved, sizeof u->saved, "%s", LEGACY[i].saved);
        u->kind = LEGACY[i].kind;
        u->codepage = LEGACY[i].codepage;
        u->release = -1;
        u->always = i < N_ALWAYS;
        u->present = first_of(firmware_dir, LEGACY[i].firmware, u->firmware, sizeof u->firmware);
        if (LEGACY[i].state[0]) {
            /* a unit that starts from a shipped state can run only with it */
            u->present &= first_of(firmware_dir, LEGACY[i].state, u->factory, sizeof u->factory);
        }
        n++;
    }
    first_release = n;
    if (found)
        scan(firmware_dir, 1, found, &nf, EMC_MAX);
    for (i = 0; found && i < nf && n < cap; i++) {
        emc_unit *u = &out[n];
        int k = found[i].release;
        if (covered(k) || (blv_release_model(k) != BL_MODEL_BRAILLE_LITE && blv_release_model(k) != BL_MODEL_BNS2000
                           && blv_release_model(k) != BL_MODEL_BNS640))
            continue;
        memset(u, 0, sizeof *u);
        u->name = blv_release_name(k);
        u->key = u->ini = blv_release_id(k);
        snprintf(u->saved, sizeof u->saved, "%s.state", blv_release_id(k));
        u->kind = EMU_BRAILLE_LITE;
        u->codepage = blv_release_code_page(k) > 0 ? blv_release_code_page(k) : BLX_CP850;
        u->release = k;
        u->present = 1;
        snprintf(u->firmware, sizeof u->firmware, "%s", found[i].path);
        n++;
    }
    /* the control: a release unit listed whose firmware is not there */
    if (emc_catalog_break && n < cap) {
        for (i = 0; i < blv_firmware_count(); i++) {
            int listed = 0, j;
            for (j = first_release; j < n; j++)
                listed |= out[j].release == i;
            if (!listed && !covered(i)) {
                emc_unit *u = &out[n++];
                memset(u, 0, sizeof *u);
                u->name = blv_release_name(i);
                u->key = u->ini = blv_release_id(i);
                snprintf(u->saved, sizeof u->saved, "%s.state", blv_release_id(i));
                u->kind = EMU_BRAILLE_LITE;
                u->codepage = BLX_CP850;
                u->release = i;
                u->present = 1;
                snprintf(u->firmware, sizeof u->firmware, "%s/%s.BNS", firmware_dir, blv_release_id(i));
                break;
            }
        }
    }
    qsort(out + first_release, (size_t)(n - first_release), sizeof *out, by_name);
    free(found);
    return n;
}

int emc_find(const emc_unit *units, int n, const char *ini)
{
    int i;
    for (i = 0; ini && i < n; i++)
        if (!strcmp(units[i].ini, ini))
            return units[i].present || units[i].always ? i : 0;
    return 0;
}

int emc_needs_factory(const emc_unit *u)
{
    return u->release >= 0 && !u->factory[0];
}

int emc_make_factory(const emc_unit *u, const char *out_path, blv_state_progress progress, void *ctx, char *err,
                     int errlen)
{
    if (!emc_needs_factory(u)) {
        snprintf(err, errlen, "%s ships its factory state", u->name);
        return 0;
    }
    if (!blv_make_release_state(u->firmware, u->release, out_path, progress, ctx, err, errlen))
        return 0;
    if (!blv_state_check(u->firmware, out_path)) {
        remove(out_path);
        snprintf(err, errlen, "the state made for %s is not the one its release lists", u->name);
        return 0;
    }
    return 1;
}

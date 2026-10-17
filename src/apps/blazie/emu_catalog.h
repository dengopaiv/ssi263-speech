/* emu_catalog.h -- the units an emulator can offer from its firmware folder: one list for every shell (Windows,
 * GTK, the terminal, the BT Speak's, Apple's unit tab, Android's unit screen), so none keeps its own.
 *
 * Two parts.  The eight units the emulators always had, exactly as before -- their names, the short keys the command
 * line takes, the saved-state file names and settings values are users' data and never change.  Then every release
 * in the release table (../../csrc/blazie/bl_languages.txt) that none of those covers, but only when its firmware is
 * in the folder: no firmware, no unit (Tomi).  A release unit has no shipped factory state: emc_make_factory makes it,
 * by the release's own recipe, the first time it starts.
 */
#ifndef EMU_CATALOG_H
#define EMU_CATALOG_H

#include "../../csrc/blazie/bl_state.h"     /* blv_state_progress */

#define EMC_PATH 1024
#define EMC_MAX 64

typedef struct {
    const char *name;                       /* "Braille Lite 2000 (English)" */
    const char *key;                        /* the command line's: "bl-en"; a release's id */
    const char *ini;                        /* the settings' value for the last unit: "english"; a release's id */
    char saved[80];                         /* its memory's file name in the save folder: "english.state" */
    int kind;                               /* emu_unit.h EMU_BRAILLE_LITE / EMU_TYPE_N_SPEAK */
    int codepage;                           /* its files' names (bl_files_xfer.h BLX_CP850 / 852) */
    int release;                            /* its row in the release table, -1 for one not on it */
    int always;                             /* listed even without its firmware (the first four: where to put it) */
    int present;                            /* its firmware is in the folder */
    char firmware[EMC_PATH];                /* where it is (or, when absent, where it is looked for first) */
    char factory[EMC_PATH];                 /* its shipped factory state; "" when there is none: a Type 'n Speak's
                                               cold start, or a release's state made on first start */
} emc_unit;

/* The units of firmware_dir, in menu order: the eight, always (`present` says whether each can run; a menu shows the
   first four, marked `always`, either way, and the others only when present), then the releases found (any .BNS in
   the folder or one below it, by its image's sha256), by name -- present, every one.  Returns how many were written
   to out (at most cap). */
int emc_list(const char *firmware_dir, emc_unit *out, int cap);

/* The unit whose settings value is ini, or 0 (the English Braille Lite) when there is none or it is not here now. */
int emc_find(const emc_unit *units, int n, const char *ini);

/* 1 when the unit's first start (no saved memory yet) needs emc_make_factory: a release unit, which ships no factory
   state. */
int emc_needs_factory(const emc_unit *u);

/* A release unit's factory state, made from its firmware by the release's recipe (blv_make_release_state) and checked
   against the table's hash (blv_state_check), written to out_path.  1 on success; 0 with the reason in err (and
   out_path removed).  English-shaped recipes take a few seconds on a desktop. */
int emc_make_factory(const emc_unit *u, const char *out_path, blv_state_progress progress, void *ctx, char *err,
                     int errlen);

/* The test's control (test_catalog.c sets it; a shell never does): nonzero lists a release unit whose firmware is
   missing, so the "no firmware, no unit" case must fail. */
extern int emc_catalog_break;

#endif

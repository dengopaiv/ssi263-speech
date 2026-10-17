/* ssa_unit.c -- see ssa_unit.h. */
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <direct.h>
#define mkdir_one(p) _mkdir(p)
#else
#define mkdir_one(p) mkdir(p, 0700)
#endif

#include "ssa_unit.h"
#include "chords.h"
#include "emu_unit.h"
#include "keys.h"
#include "tns_term.h"
#include "blazie/bl_files.h"
#include "blazie/bl_files_state.h"
#include "blazie/bl_files_xfer.h"

int ssa_unit_break;

struct ssa_unit {
    pthread_mutex_t lock;
    emu_unit *emu;
    emc_unit info;
    char saved[EMC_PATH];                   /* its memory's file */
    chord_state chord;
    int tns_down[16];                        /* the Type 'n Speak's keys down now (their down codes), to lift them */
    int n_tns;
};

static int is_file(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (f)
        fclose(f);
    return f != NULL;
}

int ssa_unit_list(const char *dir, emc_unit *out, int cap)
{
    emc_unit *all = (emc_unit *)calloc(EMC_MAX, sizeof *all);
    int i, n, k = 0;
    if (!all)
        return 0;
    n = emc_list(dir, all, EMC_MAX);
    for (i = 0; i < n && k < cap; i++)
        if (all[i].present)
            out[k++] = all[i];
    free(all);
    return k;
}

ssa_unit *ssa_unit_start(const char *dir, const char *key, const char *saved_dir, double rate, int idle,
                         blv_state_progress progress, void *ctx, char *err, int errlen)
{
    emc_unit *all = (emc_unit *)calloc(EMC_MAX, sizeof *all);
    ssa_unit *u = (ssa_unit *)calloc(1, sizeof *u);
    const char *state = NULL;
    char fresh[EMC_PATH + 8];
    int i, n, found = -1;
    if (!all || !u) {
        snprintf(err, (size_t)errlen, "out of memory");
        free(all);
        free(u);
        return NULL;
    }
    n = emc_list(dir, all, EMC_MAX);
    for (i = 0; i < n && found < 0; i++)
        if (all[i].present && !strcmp(all[i].key, key))
            found = i;
    if (found < 0) {
        snprintf(err, (size_t)errlen, "its firmware is not imported");
        free(all);
        free(u);
        return NULL;
    }
    u->info = all[found];
    free(all);
    mkdir_one(saved_dir);
    snprintf(u->saved, sizeof u->saved, "%s/%s", saved_dir, u->info.saved);
    if (is_file(u->saved))
        state = u->saved;                       /* its own memory, as it was left */
    else if (emc_needs_factory(&u->info)) {     /* a release unit's first start: its state by its own recipe */
        snprintf(fresh, sizeof fresh, "%s.new", u->saved);
        if (!emc_make_factory(&u->info, fresh, progress, ctx, err, errlen) || rename(fresh, u->saved) != 0) {
            remove(fresh);
            free(u);
            return NULL;
        }
        state = u->saved;
    } else if (u->info.factory[0])
        state = u->info.factory;                /* a shipped unit's factory state, only read */
    /* else a Type 'n Speak's cold start: the unit asks to set itself up */
    u->emu = emu_create(u->info.kind, u->info.firmware, state, rate, 0, err, errlen);
    if (!u->emu) {
        free(u);
        return NULL;
    }
    emu_set_idle(u->emu, idle, 1, 1, 1);
    chord_reset(&u->chord);
    pthread_mutex_init(&u->lock, NULL);
    return u;
}

int ssa_unit_save(ssa_unit *u)
{
    char fresh[EMC_PATH + 8];
    int ok;
    if (!u)
        return 1;
    snprintf(fresh, sizeof fresh, "%s.new", u->saved);
    pthread_mutex_lock(&u->lock);
    ok = emu_save(u->emu, fresh) == 1;
    pthread_mutex_unlock(&u->lock);
    if (ok) {
        remove(u->saved);                       /* Windows' rename never replaces (the desktop test) */
        ok = rename(fresh, u->saved) == 0;
    }
    return ok;
}

int ssa_unit_stop(ssa_unit *u)
{
    int ok;
    if (!u)
        return 1;
    ok = ssa_unit_save(u);
    emu_destroy(u->emu);
    pthread_mutex_destroy(&u->lock);
    free(u);
    return ok;
}

void ssa_unit_render(ssa_unit *u, short *out, int n)
{
    pthread_mutex_lock(&u->lock);
    emu_render(u->emu, out, n);
    pthread_mutex_unlock(&u->lock);
}

/* a Braille Lite key's chords.h bit (bl_keys.c's defaults), 0 for none */
static int chord_bit(int key)
{
    switch (key >= 'A' && key <= 'Z' ? key - 'A' + 'a' : key) {
    case 'f': return ssa_unit_break == 1 ? CHORD_DOT(4) : CHORD_DOT(1);
    case 'd': return CHORD_DOT(2);
    case 's': return CHORD_DOT(3);
    case 'j': return ssa_unit_break == 1 ? CHORD_DOT(1) : CHORD_DOT(4);
    case 'k': return CHORD_DOT(5);
    case 'l': return CHORD_DOT(6);
    case ' ': return CHORD_SPACE;
    case ';': return CHORD_ADVANCE;
    case 'a': return CHORD_BACK;
    default: return 0;
    }
}

int ssa_unit_key(ssa_unit *u, int key, int down)
{
    int taken = 0;
    pthread_mutex_lock(&u->lock);
    if (u->info.kind == EMU_TYPE_N_SPEAK) {
        int code = tns_code_of(key), i;
        if (code) {
            taken = 1;
            for (i = 0; i < u->n_tns && u->tns_down[i] != code; i++)
                ;
            if (down && i == u->n_tns && u->n_tns < 16) {        /* a key held down again is not pressed again */
                u->tns_down[u->n_tns++] = code;
                emu_key(u->emu, code);
            } else if (!down && i < u->n_tns) {
                u->tns_down[i] = u->tns_down[--u->n_tns];
                emu_key(u->emu, code & 0x7F);
            }
        }
    } else {
        int bit = chord_bit(key), chord;
        if (bit) {
            taken = 1;
            if (down) {
                chord_down(&u->chord, bit);
                emu_keys_down(u->emu, u->chord.down);
            } else {
                chord = chord_up(&u->chord, bit);
                emu_keys_down(u->emu, u->chord.down);
                if (chord)
                    emu_key(u->emu, chord);
            }
        }
    }
    pthread_mutex_unlock(&u->lock);
    return taken;
}

void ssa_unit_release_keys(ssa_unit *u)
{
    pthread_mutex_lock(&u->lock);
    chord_reset(&u->chord);
    if (u->info.kind == EMU_TYPE_N_SPEAK)
        while (u->n_tns)
            emu_key(u->emu, u->tns_down[--u->n_tns] & 0x7F);
    else
        emu_keys_down(u->emu, 0);
    pthread_mutex_unlock(&u->lock);
}

int ssa_unit_braille(ssa_unit *u, unsigned char *cells, int cap)
{
    int n;
    pthread_mutex_lock(&u->lock);
    n = emu_braille(u->emu, cells, cap);
    pthread_mutex_unlock(&u->lock);
    return n;
}

const char *ssa_unit_name(const ssa_unit *u)
{
    return u->info.name;
}

int ssa_unit_kind(const ssa_unit *u)
{
    return u->info.kind;
}

int ssa_unit_model(ssa_unit *u)
{
    int m;
    pthread_mutex_lock(&u->lock);
    m = emu_model(u->emu);
    pthread_mutex_unlock(&u->lock);
    return m;
}

void ssa_unit_set_volume(ssa_unit *u, int volume)
{
    pthread_mutex_lock(&u->lock);
    emu_set_volume(u->emu, volume);
    pthread_mutex_unlock(&u->lock);
}

void ssa_unit_set_quick(ssa_unit *u, int on)
{
    pthread_mutex_lock(&u->lock);
    emu_set_quick(u->emu, on);
    pthread_mutex_unlock(&u->lock);
}

void ssa_unit_set_idle(ssa_unit *u, int sound, int keep_open, int pop_click, int tick)
{
    pthread_mutex_lock(&u->lock);
    emu_set_idle(u->emu, sound, keep_open, pop_click, tick);
    pthread_mutex_unlock(&u->lock);
}

int ssa_unit_add_files(const char *state, int codepage, int n, const char *const *names,
                       const unsigned char *const *data, const unsigned long *sizes, const unsigned *times,
                       const unsigned *dates, int replace, int *added, int *replaced, char *msg, int msglen)
{
    bls_unit unit;
    blf_fs *fs;
    blx_report report;
    char before[EMC_PATH + 16];
    int got;
    msg[0] = 0;
    if (n <= 0) {
        snprintf(msg, (size_t)msglen, "No files were chosen.");
        return 0;
    }
    if (!bls_load(state, &unit, msg, msglen))
        return 0;
    fs = blf_open(unit.model, unit.ram, unit.flash, unit.flash_size, msg, msglen);
    if (!fs) {
        bls_free(&unit);
        return 0;
    }
    blx_report_init(&report);
    got = blx_add_cp(fs, codepage, n, names, data, sizes, times, dates, replace, &report, msg, msglen);
    if (got == BLX_ADD_EXISTS) {               /* nothing changed: the names it has already, one a line */
        const char *p = report.log ? report.log : "";
        int len = 0;
        while (*p && len < msglen - 1) {
            const char *end = strchr(p, '\n');
            size_t l = end ? (size_t)(end - p) : strlen(p);
            if (l > 7 && !strncmp(p, "exists ", 7)) {
                int take = (int)(l - 7) < msglen - 2 - len ? (int)(l - 7) : msglen - 2 - len;
                memcpy(msg + len, p + 7, (size_t)take);
                len += take;
                msg[len++] = '\n';
            }
            p = end ? end + 1 : p + l;
        }
        msg[len] = 0;
        got = -1;
    } else if (got == 1 && blf_check(fs, msg, msglen) == 1) {
        FILE *in = fopen(state, "rb"), *out;
        snprintf(before, sizeof before, "%s.before-import", state);   /* the memory as it was, beside it */
        out = in ? fopen(before, "wb") : NULL;
        if (in && out) {
            unsigned char buf[65536];
            size_t k;
            while ((k = fread(buf, 1, sizeof buf, in)) > 0)
                fwrite(buf, 1, k, out);
        }
        if (in) fclose(in);
        if (out) fclose(out);
        got = ssa_unit_break == 2 ? 1 : bls_save(state, &unit, msg, msglen) ? 1 : 0;   /* 2: the control, unsaved */
        if (added) *added = report.added;
        if (replaced) *replaced = report.replaced;
    } else
        got = 0;
    blx_report_free(&report);
    blf_close(fs);
    bls_free(&unit);
    return got;
}

int ssa_unit_flash_busy(ssa_unit *u)
{
    int busy;
    pthread_mutex_lock(&u->lock);
    busy = emu_flash(u->emu, NULL);
    pthread_mutex_unlock(&u->lock);
    return busy;
}

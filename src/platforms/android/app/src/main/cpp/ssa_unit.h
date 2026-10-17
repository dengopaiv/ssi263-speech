/* ssa_unit.h -- the Braille Lite unit screen's one running unit (UnitActivity.kt), as Apple's UnitRunner.swift runs
 * it, in C so the lock lives beside the unit: emu_unit.h's unit, its sound pulled by the audio thread (ssa_unit_render,
 * 22050 Hz), its keys pushed as they go down and come up, its display read as cells, its memory saved.
 *
 * The keys are keys.h's (the JNI glue turns Android's key codes into them: a hardware keyboard's scan code by its
 * place, evdev_key_of, so another layout's keyboard chords the same; a key with no scan code by its character):
 *   - a Braille Lite (or Braille 'n Speak): bl_keys.c's defaults, as every emulator shell has them -- F D S J K L dots
 *     1 to 6, the space bar, ; the advance bar and A the back bar -- each going down and up, the chord sent when the
 *     last comes up (chords.c), the keys held passed to the unit as they move, so a chord held while it starts is
 *     read there (i-chord: the cold reset);
 *   - a Type 'n Speak: every key its own key event, down and up (tns_term.h tns_code_of), Shift, Ctrl and Alt keys
 *     of their own.
 * The audio thread and the keys come from different threads: one mutex serialises every call.
 *
 * Portable C (no JNI, no Android): test_unit_native.c runs it on the desktop and on the phone.
 */
#ifndef SSA_UNIT_H
#define SSA_UNIT_H

#include "emu_catalog.h"

typedef struct ssa_unit ssa_unit;

/* The units the data folder can run: emc_list's, present ones only (never a unit without its firmware).  How many
   were written to out (at most cap). */
int ssa_unit_list(const char *dir, emc_unit *out, int cap);

/* Starts the unit `key` (emc_unit's key) of the data folder `dir`, its memory in `saved_dir` (made if missing): the
   saved memory when there is one, else its factory state (a release unit's made first by its own recipe, which takes
   a while: progress, when given, is called with 0..1), else a Type 'n Speak's cold start.  idle: emu_set_idle's sound
   (0 silent, 1 hiss, 2 whine, 3 as the unit).  NULL with the reason in err. */
ssa_unit *ssa_unit_start(const char *dir, const char *key, const char *saved_dir, double rate, int idle,
                         blv_state_progress progress, void *ctx, char *err, int errlen);
/* Its memory into its file: written beside it as .new, then put in place.  1 when saved. */
int ssa_unit_save(ssa_unit *u);
/* Saves it and frees it (NULL is fine).  1 when the save worked. */
int ssa_unit_stop(ssa_unit *u);

/* n samples of the unit running in real time (16-bit mono at the start's rate). */
void ssa_unit_render(ssa_unit *u, short *out, int n);
/* A key (keys.h: a character, 'f', ';', ' ', or K_*) went down (1) or came up (0).  1 when it is one of the unit's
   keys (taken), 0 when not (left to the screen: Tab, Back ...). */
int ssa_unit_key(ssa_unit *u, int key, int down);
/* Focus left the keyboard: a chord half pressed is dropped, the keys and bars come up. */
void ssa_unit_release_keys(ssa_unit *u);
/* The display as the firmware last latched it (eight-dot cells, as Unicode braille's low byte); 0 for a unit with no
   display, and for a Braille Lite before its first latch. */
int ssa_unit_braille(ssa_unit *u, unsigned char *cells, int cap);

const char *ssa_unit_name(const ssa_unit *u);
int ssa_unit_kind(const ssa_unit *u);          /* emu_unit.h EMU_BRAILLE_LITE / EMU_TYPE_N_SPEAK */
int ssa_unit_model(ssa_unit *u);               /* emu_unit.h EMU_MODEL_* */
void ssa_unit_set_volume(ssa_unit *u, int volume);
void ssa_unit_set_quick(ssa_unit *u, int on);
/* emu_set_idle: the idle channel (0 silent, 1 hiss, 2 whine, 3 as the unit), how long it stays open (0 off, 1 until
   the unit clicks off, 2 always), the pop and click, the 10 Hz tick */
void ssa_unit_set_idle(ssa_unit *u, int sound, int keep_open, int pop_click, int tick);
/* 1 while the unit erases or writes its file flash (switching it off then would lose the write) */
int ssa_unit_flash_busy(ssa_unit *u);

/* The tests' control (an app never sets it): 1 swaps dots 1 and 4 (F and J), so a chord's check must fail. */
extern int ssa_unit_break;

#endif

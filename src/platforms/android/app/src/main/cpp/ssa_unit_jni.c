/* ssa_unit_jni.c -- the JNI bridge from Kotlin (UnitNative.kt) to the Braille Lite unit screen's unit (ssa_unit.h).
 *
 * Thin, as ssa_jni.c: strings, the PCM buffer and the display cross the boundary; the unit and its lock are
 * ssa_unit's.  A unit is a handle (a jlong); the screen has one at a time.  The one thing done here is Android's: a
 * key becomes keys.h's -- a hardware keyboard's scan code (a Linux input key code) by the key's place
 * (evdev_linux.c's evdev_key_of, the BT Speak's and the Linux shells' table), so another layout's keyboard chords the
 * same; a key with no scan code (an on-screen keyboard's) by the character it types.
 */
#include <jni.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "ssa_unit.h"
#include "evdev_linux.h"
#include "emu_unit.h"

static char g_unit_error[300];
static volatile double g_unit_progress;

#define FN(name) Java_com_ssi263speech_tts_UnitNative_##name
#define UNIT(h) ((ssa_unit *)(intptr_t)(h))

static int progress(void *ctx, double done)
{
    (void)ctx;
    g_unit_progress = done;
    return 1;                                   /* go on */
}

/* The units the data folder can run: "key\tname\tkind\tsaved" each (kind: 0 Braille Lite, 1 Type 'n Speak; saved:
   its memory's file name). */
JNIEXPORT jobjectArray JNICALL FN(nativeUnitList)(JNIEnv *env, jclass cls, jstring jdir)
{
    static emc_unit units[EMC_MAX];             /* one caller at a time: the screen's own thread */
    const char *dir = (*env)->GetStringUTFChars(env, jdir, NULL);
    jclass str = (*env)->FindClass(env, "java/lang/String");
    jobjectArray out;
    char row[200];
    int i, n;
    (void)cls;
    if (!dir || !str) return NULL;
    n = ssa_unit_list(dir, units, EMC_MAX);
    (*env)->ReleaseStringUTFChars(env, jdir, dir);
    out = (*env)->NewObjectArray(env, n, str, NULL);
    for (i = 0; out && i < n; i++) {
        snprintf(row, sizeof row, "%s\t%s\t%d\t%s", units[i].key, units[i].name, units[i].kind, units[i].saved);
        (*env)->SetObjectArrayElement(env, out, i, (*env)->NewStringUTF(env, row));
    }
    return out;
}

/* Starts a unit (ssa_unit_start): its handle, or 0 with the reason in nativeUnitError. */
JNIEXPORT jlong JNICALL FN(nativeUnitStart)(JNIEnv *env, jclass cls, jstring jdir, jstring jkey, jstring jsaved,
                                            jint rate, jint idle)
{
    const char *dir = (*env)->GetStringUTFChars(env, jdir, NULL);
    const char *key = (*env)->GetStringUTFChars(env, jkey, NULL);
    const char *saved = (*env)->GetStringUTFChars(env, jsaved, NULL);
    ssa_unit *u = NULL;
    (void)cls;
    g_unit_progress = 0;
    g_unit_error[0] = 0;
    if (dir && key && saved)
        u = ssa_unit_start(dir, key, saved, (double)rate, idle, progress, NULL, g_unit_error, sizeof g_unit_error);
    if (dir) (*env)->ReleaseStringUTFChars(env, jdir, dir);
    if (key) (*env)->ReleaseStringUTFChars(env, jkey, key);
    if (saved) (*env)->ReleaseStringUTFChars(env, jsaved, saved);
    return (jlong)(intptr_t)u;
}

JNIEXPORT jstring JNICALL FN(nativeUnitError)(JNIEnv *env, jclass cls)
{
    (void)cls;
    return (*env)->NewStringUTF(env, g_unit_error);
}

/* A release unit's first start: how far its state's recipe has come, 0..1 */
JNIEXPORT jdouble JNICALL FN(nativeUnitProgress)(JNIEnv *env, jclass cls)
{
    (void)env; (void)cls;
    return g_unit_progress;
}

JNIEXPORT jboolean JNICALL FN(nativeUnitStop)(JNIEnv *env, jclass cls, jlong h)
{
    (void)env; (void)cls;
    return ssa_unit_stop(UNIT(h)) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL FN(nativeUnitSave)(JNIEnv *env, jclass cls, jlong h)
{
    (void)env; (void)cls;
    return ssa_unit_save(UNIT(h)) ? JNI_TRUE : JNI_FALSE;
}

/* n samples into pcm (16-bit mono) */
JNIEXPORT void JNICALL FN(nativeUnitRender)(JNIEnv *env, jclass cls, jlong h, jshortArray jpcm, jint n)
{
    jshort *pcm = (*env)->GetShortArrayElements(env, jpcm, NULL);
    (void)cls;
    if (!pcm) return;
    if (n > (*env)->GetArrayLength(env, jpcm)) n = (*env)->GetArrayLength(env, jpcm);
    ssa_unit_render(UNIT(h), (short *)pcm, n);
    (*env)->ReleaseShortArrayElements(env, jpcm, pcm, 0);
}

/* A key went down or came up: its scan code (KeyEvent.getScanCode, 0 for none) or else the character it types
   (KeyEvent.getUnicodeChar, 0 for none).  True when the unit took it. */
JNIEXPORT jboolean JNICALL FN(nativeUnitKey)(JNIEnv *env, jclass cls, jlong h, jint scan, jint ch, jboolean down)
{
    int key = scan > 0 ? evdev_key_of(scan) : ch;
    (void)env; (void)cls;
    if (key <= 0) return JNI_FALSE;
    return ssa_unit_key(UNIT(h), key, down == JNI_TRUE) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT void JNICALL FN(nativeUnitReleaseKeys)(JNIEnv *env, jclass cls, jlong h)
{
    (void)env; (void)cls;
    ssa_unit_release_keys(UNIT(h));
}

/* The display as Unicode braille (U+2800 + each cell's dots); "" for a unit with no display */
JNIEXPORT jstring JNICALL FN(nativeUnitBraille)(JNIEnv *env, jclass cls, jlong h)
{
    unsigned char cells[EMU_CELLS];
    jchar text[EMU_CELLS];
    int i, n = ssa_unit_braille(UNIT(h), cells, EMU_CELLS);
    (void)cls;
    for (i = 0; i < n; i++)
        text[i] = (jchar)(0x2800 + cells[i]);
    return (*env)->NewString(env, text, n);
}

JNIEXPORT jint JNICALL FN(nativeUnitKind)(JNIEnv *env, jclass cls, jlong h)
{
    (void)env; (void)cls;
    return ssa_unit_kind(UNIT(h));
}

/* emu_unit.h EMU_MODEL_*: 0 Braille Lite 2000, 1 Braille 'n Speak 2000, 2 Type 'n Speak, 3 Braille 'n Speak 640 */
JNIEXPORT jint JNICALL FN(nativeUnitModel)(JNIEnv *env, jclass cls, jlong h)
{
    (void)env; (void)cls;
    return ssa_unit_model(UNIT(h));
}

JNIEXPORT void JNICALL FN(nativeUnitVolume)(JNIEnv *env, jclass cls, jlong h, jint volume)
{
    (void)env; (void)cls;
    ssa_unit_set_volume(UNIT(h), volume);
}

JNIEXPORT void JNICALL FN(nativeUnitQuick)(JNIEnv *env, jclass cls, jlong h, jboolean on)
{
    (void)env; (void)cls;
    ssa_unit_set_quick(UNIT(h), on == JNI_TRUE);
}

JNIEXPORT jboolean JNICALL FN(nativeUnitFlashBusy)(JNIEnv *env, jclass cls, jlong h)
{
    (void)env; (void)cls;
    return ssa_unit_flash_busy(UNIT(h)) ? JNI_TRUE : JNI_FALSE;
}

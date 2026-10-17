/* bl_numbers.h -- the Braille Lite driver's "Custom number processing" (nvda/blazie/synthDrivers/blazie.py _numbers and
 * _money, the driver's default: on) in C, for bl_voice's blv_set_numbers.
 *
 * English: numbers as words (numwords.c's nw_normalise), except dollar amounts, which go to the firmware as they are
 * up to $999,999,999,999 (it says "$25" itself, and drops a "$" in front of words); from a trillion up those become
 * words here.  Spanish: Spain's convention, "1.234.567" one number and "3,5" tres coma cinco (numwords_es.c).
 *
 * It lives apart from bl_voice.c so the voice still links without the number words (bl.dll, the add-on's library,
 * has none of them): a front end that wants them links this file, numwords.c and numwords_es.c and passes bl_numbers
 * to blv_set_numbers.  nvda/tools/voice_text_equiv.py --numbers holds it to the driver byte for byte.  MIT.
 */
#ifndef BL_NUMBERS_H
#define BL_NUMBERS_H

#include "bl_host.h"

#ifdef __cplusplus
extern "C" {
#endif

/* _numbers(text, lang): text is the voice's cleaned text (UTF-8; 7-bit for the English unit), encoding the voice's
   (bl_voice.h BLV_LATIN1 = English, BLV_CP850 = Spanish).  A malloc'd UTF-8 string, NULL when out of memory. */
BL_API char *bl_numbers(const char *utf8, int encoding);
/* _trillions(text): the number processing of a unit whose own reader folds a trillion into billions (bl_firmware.h
   BLV_TRILLIONS_FOLD; every other voice's number words are its own): a number of 13 digits or more goes to the unit a
   digit at a time, "1 2 3 ...", each digit said in the unit's own language; one of 12 or fewer is left as it is.  A
   number is a run of digits, or one to three digits and groups of exactly three after the same ',' or '.'; what
   follows it (a decimal part) is left as it is.  Same signature as bl_numbers, for blv_set_numbers.  Plain C: it
   needs no number words, and works on the bytes (UTF-8 never puts a digit, ',' or '.' inside a character). */
BL_API char *bl_trillions(const char *utf8, int encoding);
/* The tests' control (an app never sets it): nonzero, bl_trillions leaves every number as it is. */
BL_API extern int bl_trillions_break;

#ifdef __cplusplus
}
#endif
#endif

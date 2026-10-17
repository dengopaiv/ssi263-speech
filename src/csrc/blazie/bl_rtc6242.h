/* bl_rtc6242.h -- the Braille 'n Speak 640's clock: an OKI M6242B (MSM6242B) real-time clock on the CPU's bus, its 16
 * four-bit registers at ports 60h-6Fh (register n at 60h + n).  Found by running the 640's own firmware (issue
 * #15's BSPENG.BNS): at its start it reads control register F and writes 04h (24-hour mode); to read the time it
 * writes 01h to control register D (HOLD), polls D until BUSY is 0, then reads the digits -- the data sheet's
 * procedure.  Without the chip it read BUSY as 1 forever and spoke no further than "ready".
 *
 * From OKI's data sheet (1990 Microprocessor Data Book, MSM6242BRS/GS-VK/JS; register addresses as NetBSD's
 * msm6242breg.h): 0 S1, 1 S10, 2 MI1, 3 MI10, 4 H1, 5 H10 (bit 2 PM/AM in 12-hour mode, read 0 in 24-hour mode), 6 D1,
 * 7 D10, 8 MO1, 9 MO10, A Y1, B Y10, C W (the weekday, 0-6, Sunday 0), all BCD; D: HOLD (bit 0), BUSY (1), IRQ FLAG
 * (2), 30-second adjust (3); E: MASK, ITRPT/STND, t0, t1 (the STD.P output: kept, not driven -- the 640's firmware was
 * not seen to use it); F: REST (0: the sub-second divider held in reset while 1), STOP (1), 24/12 (2: 1 = 24 hours,
 * written only while REST is 1), TEST (3: ignored).  The counting is the chip's, digit by digit: a carry into the
 * day past the month's last (a Feb 29 written in a common year, a Nov 31) gives the 1st of the next month; every
 * fourth year (00 included) is a leap year.  BUSY always reads 0: a carry here is never half done when the firmware
 * looks.  A carry while HOLD is 1 is given when HOLD goes back to 0.
 *
 * Portable C99.  Time is the board's: T-states of the clock blr_init is given (bl_board's now_t). */
#ifndef BL_RTC6242_H
#define BL_RTC6242_H

#include "bl_clock.h"

#define BLR_PORT 0x60                /* register 0's port on the BNS 640 */

typedef struct {
    unsigned char d[16];             /* the registers as the chip holds them, 4 bits each (D's BUSY never set) */
    unsigned long long sub;          /* T-states into the current second */
    unsigned long long last;         /* the board time it was last brought up to */
    unsigned held;                   /* seconds counted while HOLD was 1, given when it goes back to 0 */
    double hz;                       /* the board clock */
} blr_rtc;

/* A clock at 2000-01-01 00:00:00, a Saturday, in 24-hour mode and running, as a unit whose clock was once set up;
   `now`: the board time. */
void blr_init(blr_rtc *r, double hz, unsigned long long now);
/* The time from a calendar time (the host's): the year's last two digits, the weekday worked out. */
void blr_set(blr_rtc *r, const blc_time *t, unsigned long long now);
/* Its time as a calendar time, the year in 2000-2099. */
void blr_get(blr_rtc *r, blc_time *t, unsigned long long now);
/* A register (0-15) read and written by the CPU at board time `now`: the four bits, the upper four 0. */
unsigned char blr_read(blr_rtc *r, int reg, unsigned long long now);
void blr_write(blr_rtc *r, int reg, unsigned char v, unsigned long long now);
/* The chip in a state's tail (BLR_SAVE_SIZE bytes, the clock controller's size, so the state's readers tell its sizes
   alike), brought up to `now` first, with the host's time it was saved at (seconds; -1 unknown); and back, at board
   time `now`.  blr_load returns 0 for bytes that are not a saved chip (a Braille Lite's controller). */
#define BLR_SAVE_SIZE 64
void blr_save(blr_rtc *r, long long saved_at, unsigned long long now, unsigned char *buf);
int blr_load(blr_rtc *r, const unsigned char *buf, long long *saved_at, unsigned long long now);
/* The time the unit was off (seconds): the chip kept counting on its battery, unless stopped or reset. */
void blr_advance_off(blr_rtc *r, long long seconds);
/* The tests' controls (an app never sets it): 1 no leap years, 2 the carries counted under HOLD dropped, 3 the chip
   left out of a saved state (bl_save_state), 4 the time off not counted. */
extern int blr_break;

#endif

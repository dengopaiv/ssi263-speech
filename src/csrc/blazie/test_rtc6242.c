/* test_rtc6242.c -- the BNS 640's OKI M6242B clock (bl_rtc6242.h) on its own, as the data sheet says it behaves.
 *
 *   test_rtc6242 [break]      break 1: no leap years, 2: the carries counted under HOLD dropped, 4: the time off
 *                             not counted (the controls: the checks for them must fail)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bl_rtc6242.h"

#define HZ 6144000.0
#define SEC 6144000ULL

static int failures;

static void check(const char *name, int ok, const char *detail)
{
    printf("%-4s %-34s %s\n", ok ? "ok" : "FAIL", name, detail);
    failures += !ok;
}

/* the time as the CPU reads it, digit by digit: "YY-MM-DD hh:mm:ss w" */
static void digits(blr_rtc *r, unsigned long long now, char *out)
{
    unsigned char v[13];
    int i;
    for (i = 0; i < 13; i++)
        v[i] = blr_read(r, i, now);
    sprintf(out, "%d%d-%d%d-%d%d %d%d:%d%d:%d%d %d", v[11], v[10], v[9], v[8], v[7], v[6], v[5] & 3, v[4], v[3], v[2],
            v[1], v[0], v[12]);
}

static void start(blr_rtc *r, int y, int mo, int d, int h, int mi, int s)
{
    blc_time t = {y, mo, d, h, mi, s};
    blr_init(r, HZ, 0);
    blr_set(r, &t, 0);
}

int main(int argc, char **argv)
{
    blr_rtc r;
    char got[40], d[160];
    unsigned long long t;
    if (argc > 1)
        blr_break = atoi(argv[1]);

    start(&r, 2026, 10, 16, 21, 30, 59);
    digits(&r, 0, got);
    snprintf(d, sizeof d, "%s (want 26-10-16 21:30:59 5, a Friday)", got);
    check("set from the host", !strcmp(got, "26-10-16 21:30:59 5"), d);
    digits(&r, SEC, got);
    snprintf(d, sizeof d, "a second later %s (want 26-10-16 21:31:00 5)", got);
    check("counts", !strcmp(got, "26-10-16 21:31:00 5"), d);

    /* the firmware's read: HOLD, BUSY 0, the digits; a carry under HOLD is given when HOLD goes back to 0 */
    start(&r, 2026, 10, 16, 23, 59, 59);
    blr_write(&r, 13, 0x01, SEC / 2);
    snprintf(d, sizeof d, "control D reads %X (want 1: HOLD, BUSY 0)", blr_read(&r, 13, SEC / 2));
    check("HOLD, BUSY 0", blr_read(&r, 13, SEC / 2) == 1, d);
    digits(&r, SEC + SEC / 4, got);
    snprintf(d, sizeof d, "past the second under HOLD %s (want 23:59:59 kept)", got);
    check("HOLD keeps the digits", !strcmp(got, "26-10-16 23:59:59 5"), d);
    blr_write(&r, 13, 0x04, SEC + SEC / 4);
    digits(&r, SEC + SEC / 4, got);
    snprintf(d, sizeof d, "HOLD off %s (want 26-10-17 00:00:00 6: the day's carry given)", got);
    check("HOLD's carry given after", !strcmp(got, "26-10-17 00:00:00 6"), d);

    /* leap years: every fourth, 2000 included */
    start(&r, 2024, 2, 28, 23, 59, 59);
    digits(&r, SEC, got);
    snprintf(d, sizeof d, "2024-02-28 23:59:59 + 1 s = %s (want 24-02-29)", got);
    check("leap year", !strncmp(got, "24-02-29 00:00:00", 17), d);
    start(&r, 2025, 2, 28, 23, 59, 59);
    digits(&r, SEC, got);
    snprintf(d, sizeof d, "2025-02-28 23:59:59 + 1 s = %s (want 25-03-01)", got);
    check("common year", !strncmp(got, "25-03-01 00:00:00", 17), d);
    /* a Feb 29 written in a common year becomes Mar 1 at the day's carry (the data sheet's example) */
    start(&r, 2025, 2, 27, 23, 59, 59);
    blr_write(&r, 6, 9, 0);
    blr_write(&r, 7, 2, 0);
    digits(&r, 0, got);
    t = SEC;
    {
        char after[40];
        digits(&r, t, after);
        snprintf(d, sizeof d, "written %s, at the carry %s (want 25-03-01)", got, after);
        check("a written Feb 29 of 2025", !strncmp(got, "25-02-29", 8) && !strncmp(after, "25-03-01", 8), d);
    }
    start(&r, 2099, 12, 31, 23, 59, 59);
    digits(&r, SEC, got);
    snprintf(d, sizeof d, "99-12-31 23:59:59 + 1 s = %s (want 00-01-01)", got);
    check("the year 99 -> 00", !strncmp(got, "00-01-01 00:00:00", 17), d);

    /* 24/12: written only while REST was 1; in 12-hour mode H10 carries PM/AM */
    start(&r, 2026, 10, 16, 13, 5, 0);
    blr_write(&r, 15, 0x00, 0);              /* 24/12 = 0 with REST 0: ignored */
    snprintf(d, sizeof d, "control F %X after writing 0 with REST 0 (want 4: 24 hours kept)", blr_read(&r, 15, 0));
    check("24/12 needs REST", blr_read(&r, 15, 0) == 4, d);
    blr_write(&r, 15, 0x01, 0);              /* REST */
    blr_write(&r, 15, 0x01, 0);              /* 12-hour mode, REST still 1 */
    blr_write(&r, 15, 0x00, 0);              /* REST off */
    blr_write(&r, 4, 1, 0);                  /* 1 PM */
    blr_write(&r, 5, 0x4, 0);
    {
        blc_time g;
        blr_get(&r, &g, 0);
        snprintf(d, sizeof d, "control F %X, H10 %X, the hour %d (want 0, 4: PM, 13)", blr_read(&r, 15, 0),
                 blr_read(&r, 5, 0), g.hour);
        check("12-hour mode, PM", blr_read(&r, 15, 0) == 0 && blr_read(&r, 5, 0) == 4 && g.hour == 13, d);
    }

    /* STOP and REST: no counting */
    start(&r, 2026, 10, 16, 8, 0, 0);
    blr_write(&r, 15, 0x06, 0);              /* STOP, 24 hours */
    digits(&r, 3 * SEC, got);
    snprintf(d, sizeof d, "3 s under STOP: %s (want 08:00:00)", got);
    check("STOP", !strncmp(got + 9, "08:00:00", 8), d);
    blr_write(&r, 15, 0x04, 3 * SEC);
    digits(&r, 4 * SEC, got);
    snprintf(d, sizeof d, "running again, a second later: %s (want 08:00:01)", got);
    check("STOP off", !strncmp(got + 9, "08:00:01", 8), d);

    /* the 30-second adjustment: to the nearest minute */
    start(&r, 2026, 10, 16, 8, 0, 45);
    blr_write(&r, 13, 0x0C, 0);              /* 30 ADJ, with the IRQ bit 1 as the data sheet asks */
    digits(&r, 0, got);
    snprintf(d, sizeof d, "at :45 -> %s (want 08:01:00), control D %X (want 0)", got, blr_read(&r, 13, 0));
    check("30-second adjust", !strncmp(got + 9, "08:01:00", 8) && blr_read(&r, 13, 0) == 0, d);

    {   /* saved into a state's tail at 1.5 s past 23:59:58 and loaded into a new chip: the same digits and the same
           half second to go; then off for 400 days and 3 seconds (2024 a leap year: 2025-02-05 00:00:03, a Wednesday) */
        unsigned char buf[BLR_SAVE_SIZE];
        blr_rtc back;
        long long at = 0;
        char was[32];
        start(&r, 2024, 1, 0 + 1, 23, 59, 58);
        blr_save(&r, 1700000000LL, SEC + SEC / 2, buf);
        digits(&r, SEC + SEC / 2, was);
        blr_init(&back, HZ, 0);
        blr_load(&back, buf, &at, 10 * SEC);
        digits(&back, 10 * SEC + SEC / 2, got);
        snprintf(d, sizeof d, "saved %s, loaded %s (saved at %lld); a Braille Lite's tail refused: %s", was, got, at,
                 blr_load(&back, (const unsigned char *)"BLCLOCK1", NULL, 0) ? "no" : "yes");
        check("saved and loaded", !strcmp(was, "24-01-01 23:59:59 1") && !strcmp(got, "24-01-02 00:00:00 2")
                                  && at == 1700000000LL, d);
        blr_advance_off(&back, 400LL * 86400 + 3);
        digits(&back, 10 * SEC + SEC / 2, got);
        snprintf(d, sizeof d, "off 400 days 3 s: %s", got);
        check("kept time while off", !strcmp(got, "25-02-05 00:00:03 3"), d);
    }

    printf("%s\n", failures ? "rtc6242: FAILED" : "rtc6242: all passed");
    return failures ? 1 : 0;
}

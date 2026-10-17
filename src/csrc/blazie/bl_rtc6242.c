/* bl_rtc6242.c -- the OKI M6242B real-time clock of the Braille 'n Speak 640 (bl_rtc6242.h says what was measured). */
#include "bl_rtc6242.h"

enum { RS1, RS10, RMI1, RMI10, RH1, RH10, RD1, RD10, RMO1, RMO10, RY1, RY10, RW, RCD, RCE, RCF };
#define R_HOLD 0x1
#define R_IRQ 0x4
#define R_ADJ30 0x8
#define R_REST 0x1
#define R_STOP 0x2
#define R_H24 0x4
#define R_PMAM 0x4

/* the bits each register has (the data sheet's table: S10 0-5, H10 two digit bits and PM/AM, D10 0-3, MO10 0-1) */
static const unsigned char R_BITS[16] = {0xF, 0x7, 0xF, 0x7, 0xF, 0x7, 0xF, 0x3, 0xF, 0x1, 0xF, 0xF, 0x7, 0xF, 0xF, 0xF};

static int rtc_pair(const blr_rtc *r, int lo) { return r->d[lo] + 10 * r->d[lo + 1]; }

static void rtc_set_pair(blr_rtc *r, int lo, int v)
{
    r->d[lo] = (unsigned char)(v % 10 & R_BITS[lo]);
    r->d[lo + 1] = (unsigned char)(v / 10 & R_BITS[lo + 1]);
}

int blr_break;

static int rtc_month_days(int month, int year)
{
    if (month == 2)
        return year % 4 == 0 && blr_break != 1 ? 29 : 28;
    return month == 4 || month == 6 || month == 9 || month == 11 ? 30 : 31;
}

/* the day's carry: the weekday, then the date, the month past its last day, the year past December */
static void rtc_next_day(blr_rtc *r)
{
    int day = rtc_pair(r, RD1) + 1, month = rtc_pair(r, RMO1), year = rtc_pair(r, RY1);
    r->d[RW] = (unsigned char)((r->d[RW] + 1) % 7);
    if (day > rtc_month_days(month, year)) {
        day = 1;
        if (++month > 12) {
            month = 1;
            year = (year + 1) % 100;
            rtc_set_pair(r, RY1, year);
        }
        rtc_set_pair(r, RMO1, month);
    }
    rtc_set_pair(r, RD1, day);
}

static void rtc_next_hour(blr_rtc *r)
{
    if (r->d[RCF] & R_H24) {
        int h = r->d[RH1] + 10 * (r->d[RH10] & 3) + 1;
        r->d[RH10] &= (unsigned char)~3;
        if (h == 24) {
            h = 0;
            rtc_next_day(r);
        }
        r->d[RH1] = (unsigned char)(h % 10);
        r->d[RH10] |= (unsigned char)(h / 10);
    } else {                                 /* 12-hour mode: 11 -> 12 turns AM/PM, 12 -> 1; 12 AM starts a day */
        int h = r->d[RH1] + 10 * (r->d[RH10] & 1) + 1, pm = r->d[RH10] & R_PMAM;
        if (h == 12) {
            pm ^= R_PMAM;
            if (!pm)
                rtc_next_day(r);
        } else if (h == 13)
            h = 1;
        r->d[RH1] = (unsigned char)(h % 10);
        r->d[RH10] = (unsigned char)(h / 10 | pm);
    }
}

static void rtc_next_minute(blr_rtc *r)
{
    int m = rtc_pair(r, RMI1) + 1;
    if (m == 60) {
        m = 0;
        rtc_next_hour(r);
    }
    rtc_set_pair(r, RMI1, m);
}

static void rtc_next_second(blr_rtc *r)
{
    int s = rtc_pair(r, RS1) + 1;
    if (s == 60) {
        s = 0;
        rtc_next_minute(r);
    }
    rtc_set_pair(r, RS1, s);
}

/* time passes up to `now`: whole seconds into the counters (or held for later under HOLD), none while the divider
   is reset or stopped */
static void rtc_advance(blr_rtc *r, unsigned long long now)
{
    unsigned long long second = (unsigned long long)(r->hz + 0.5);
    unsigned long long dt = now > r->last ? now - r->last : 0;
    r->last = now;
    if (r->d[RCF] & (R_REST | R_STOP)) {
        if (r->d[RCF] & R_REST)
            r->sub = 0;
        return;
    }
    r->sub += dt;
    while (r->sub >= second) {
        r->sub -= second;
        if (r->d[RCD] & R_HOLD)
            r->held++;
        else
            rtc_next_second(r);
    }
}

void blr_init(blr_rtc *r, double hz, unsigned long long now)
{
    int i;
    for (i = 0; i < 16; i++)
        r->d[i] = 0;
    r->d[RD1] = 1;
    r->d[RMO1] = 1;
    r->d[RW] = 6;                             /* 2000-01-01, a Saturday */
    r->d[RCF] = R_H24;
    r->sub = 0;
    r->held = 0;
    r->hz = hz;
    r->last = now;
}

void blr_set(blr_rtc *r, const blc_time *t, unsigned long long now)
{
    static const int k[12] = {0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4};   /* the weekday, Sunday 0 (Sakamoto) */
    int y = t->year - (t->month < 3), hour = t->hour;
    rtc_advance(r, now);
    rtc_set_pair(r, RS1, t->second);
    rtc_set_pair(r, RMI1, t->minute);
    if (r->d[RCF] & R_H24)
        rtc_set_pair(r, RH1, hour);
    else {
        int h = hour % 12 == 0 ? 12 : hour % 12;
        r->d[RH1] = (unsigned char)(h % 10);
        r->d[RH10] = (unsigned char)(h / 10 | (hour >= 12 ? R_PMAM : 0));
    }
    rtc_set_pair(r, RD1, t->day);
    rtc_set_pair(r, RMO1, t->month);
    rtc_set_pair(r, RY1, t->year % 100);
    r->d[RW] = (unsigned char)((y + y / 4 - y / 100 + y / 400 + k[(t->month - 1) % 12] + t->day) % 7);
    r->sub = 0;
    r->held = 0;
}

void blr_get(blr_rtc *r, blc_time *t, unsigned long long now)
{
    rtc_advance(r, now);
    t->second = rtc_pair(r, RS1);
    t->minute = rtc_pair(r, RMI1);
    if (r->d[RCF] & R_H24)
        t->hour = r->d[RH1] + 10 * (r->d[RH10] & 3);
    else {
        int h = r->d[RH1] + 10 * (r->d[RH10] & 1);
        t->hour = h % 12 + (r->d[RH10] & R_PMAM ? 12 : 0);
    }
    t->day = rtc_pair(r, RD1);
    t->month = rtc_pair(r, RMO1);
    t->year = 2000 + rtc_pair(r, RY1);
}

static const unsigned char MAGIC[8] = {'B', 'L', 'R', '6', '2', '4', '2', 1};

static void put64(unsigned char *p, unsigned long long v)
{
    int i;
    for (i = 0; i < 8; i++, v >>= 8)
        p[i] = (unsigned char)(v & 0xFF);
}

static unsigned long long get64(const unsigned char *p)
{
    unsigned long long v = 0;
    int i;
    for (i = 7; i >= 0; i--)
        v = (v << 8) | p[i];
    return v;
}

void blr_save(blr_rtc *r, long long saved_at, unsigned long long now, unsigned char *buf)
{
    int i;
    rtc_advance(r, now);
    for (i = 0; i < BLR_SAVE_SIZE; i++)
        buf[i] = 0;
    for (i = 0; i < 8; i++)
        buf[i] = MAGIC[i];
    for (i = 0; i < 16; i++)
        buf[8 + i] = r->d[i];
    put64(buf + 24, r->sub);
    put64(buf + 32, r->held);
    put64(buf + 40, (unsigned long long)saved_at);
}

int blr_load(blr_rtc *r, const unsigned char *buf, long long *saved_at, unsigned long long now)
{
    int i;
    for (i = 0; i < 8; i++)
        if (buf[i] != MAGIC[i])
            return 0;
    for (i = 0; i < 16; i++)
        r->d[i] = (unsigned char)(buf[8 + i] & 0xF);
    r->sub = get64(buf + 24);
    if (r->sub >= (unsigned long long)(r->hz + 0.5))
        r->sub = 0;
    r->held = (unsigned)get64(buf + 32);
    r->last = now;
    if (saved_at)
        *saved_at = (long long)get64(buf + 40);
    return 1;
}

void blr_advance_off(blr_rtc *r, long long seconds)
{
    if (seconds <= 0 || (r->d[RCF] & (R_REST | R_STOP)) || blr_break == 4)
        return;
    for (; seconds >= 86400; seconds -= 86400)   /* a whole day on: the date's carry, the time of day the same */
        rtc_next_day(r);
    for (; seconds > 0; seconds--)
        rtc_next_second(r);
}

unsigned char blr_read(blr_rtc *r, int reg, unsigned long long now)
{
    reg &= 15;
    rtc_advance(r, now);
    if (reg == RCD)
        return (unsigned char)(r->d[RCD] & (R_HOLD | R_IRQ));   /* BUSY and the 30-second bit read 0 */
    if (reg == RH10 && (r->d[RCF] & R_H24))
        return (unsigned char)(r->d[RH10] & 3);             /* PM/AM reads 0 in 24-hour mode */
    return r->d[reg];
}

void blr_write(blr_rtc *r, int reg, unsigned char v, unsigned long long now)
{
    reg &= 15;
    v &= 0xF;
    rtc_advance(r, now);
    if (reg < RCD) {
        r->d[reg] = (unsigned char)(v & R_BITS[reg]);
        return;
    }
    if (reg == RCD) {
        int was_held = r->d[RCD] & R_HOLD;
        r->d[RCD] = (unsigned char)((v & R_HOLD) | (v & r->d[RCD] & R_IRQ));   /* writing IRQ 0 clears it */
        if (v & R_ADJ30) {                     /* rounds to the nearest minute */
            if (rtc_pair(r, RS1) >= 30)
                rtc_next_minute(r);
            rtc_set_pair(r, RS1, 0);
            r->sub = 0;
        }
        if (was_held && !(v & R_HOLD))         /* the carries counted under HOLD */
            for (; r->held; r->held--)
                if (blr_break != 2)
                    rtc_next_second(r);
        return;
    }
    if (reg == RCE) {
        r->d[RCE] = v;
        return;
    }
    {                                        /* CF: 24/12 only changes while REST was already 1 */
        unsigned char keep = (unsigned char)(r->d[RCF] & R_REST ? 0 : R_H24);
        r->d[RCF] = (unsigned char)((v & ~keep) | (r->d[RCF] & keep));
        if (r->d[RCF] & R_REST)
            r->sub = 0;
    }
}

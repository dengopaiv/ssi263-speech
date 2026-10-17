/* uhid_keys.c -- a USB keyboard that exists only in software, for the Braille Lite unit screen's device test: run over
 * adb (the shell user is in the uhid group, as scrcpy's --keyboard=uhid uses it; no root), it makes the kernel's
 * /dev/uhid announce a standard boot keyboard, and plays a script of keys going down and coming up.  Android sees a
 * hardware keyboard: real scan codes, several keys down at once -- what a Bluetooth keyboard gives, which adb's
 * `input keyevent` (no scan code, one key at a time) cannot.
 *
 *   uhid_keys 'wait 1500' 'down f d' 'wait 80' 'up f' 'up d' 'tap ;' ...
 *
 * Each argument one step: `down K...` (keys go down, in the one report), `up K...`, `tap K` (down, 60 ms, up),
 * `wait MS`.  Keys: a-z, 0-9, space, ; , . / ' - = [ ] \ ` enter esc tab backspace, lshift lctrl lalt (modifiers).
 * The device goes away at the end (every key up first).  Six keys at most down at once, as a boot keyboard reports.
 */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <linux/uhid.h>

/* the HID boot keyboard: a modifier byte, a reserved byte, six key usages (and the five LEDs it is sent) */
static const unsigned char DESCRIPTOR[] = {
    0x05, 0x01, 0x09, 0x06, 0xA1, 0x01, 0x05, 0x07, 0x19, 0xE0, 0x29, 0xE7, 0x15, 0x00, 0x25, 0x01, 0x75, 0x01,
    0x95, 0x08, 0x81, 0x02, 0x95, 0x01, 0x75, 0x08, 0x81, 0x01, 0x95, 0x05, 0x75, 0x01, 0x05, 0x08, 0x19, 0x01,
    0x29, 0x05, 0x91, 0x02, 0x95, 0x01, 0x75, 0x03, 0x91, 0x01, 0x95, 0x06, 0x75, 0x08, 0x15, 0x00, 0x25, 0x65,
    0x05, 0x07, 0x19, 0x00, 0x29, 0x65, 0x81, 0x00, 0xC0,
};

static int fd;
static unsigned char mods, keys[6];

static void sleep_ms(int ms)
{
    struct timespec t = {ms / 1000, (long)(ms % 1000) * 1000000L};
    nanosleep(&t, NULL);
}

static int send_event(struct uhid_event *ev)
{
    if (write(fd, ev, sizeof *ev) != (ssize_t)sizeof *ev) {
        fprintf(stderr, "uhid write: %s\n", strerror(errno));
        return 0;
    }
    return 1;
}

static int report(void)
{
    struct uhid_event ev;
    memset(&ev, 0, sizeof ev);
    ev.type = UHID_INPUT2;
    ev.u.input2.size = 8;
    ev.u.input2.data[0] = mods;
    memcpy(ev.u.input2.data + 2, keys, 6);
    return send_event(&ev);
}

/* a key's HID usage, or a modifier as -(its bit); 0 for none */
static int usage(const char *k)
{
    static const struct { const char *name; int usage; } NAMED[] = {
        {"space", 0x2C}, {"enter", 0x28}, {"esc", 0x29}, {"backspace", 0x2A}, {"tab", 0x2B}, {"-", 0x2D},
        {"=", 0x2E}, {"[", 0x2F}, {"]", 0x30}, {"\\", 0x31}, {";", 0x33}, {"'", 0x34}, {"`", 0x35}, {",", 0x36},
        {".", 0x37}, {"/", 0x38}, {"lctrl", -0x01}, {"lshift", -0x02}, {"lalt", -0x04},
    };
    unsigned i;
    if (k[0] >= 'a' && k[0] <= 'z' && !k[1]) return 0x04 + (k[0] - 'a');
    if (k[0] >= '1' && k[0] <= '9' && !k[1]) return 0x1E + (k[0] - '1');
    if (k[0] == '0' && !k[1]) return 0x27;
    for (i = 0; i < sizeof NAMED / sizeof NAMED[0]; i++)
        if (!strcmp(NAMED[i].name, k)) return NAMED[i].usage;
    return 0;
}

static int press(const char *k, int down)
{
    int u = usage(k), i;
    if (!u) {
        fprintf(stderr, "unknown key: %s\n", k);
        return 0;
    }
    if (u < 0) {
        mods = (unsigned char)(down ? mods | -u : mods & ~-u);
        return 1;
    }
    for (i = 0; i < 6 && keys[i] != (down ? 0 : u); i++)
        ;
    if (i == 6) {
        if (down) fprintf(stderr, "more than six keys down\n");
        return !down;                             /* a key up that was not down: nothing to do */
    }
    keys[i] = (unsigned char)(down ? u : 0);
    return 1;
}

static int step(char *s)
{
    char *verb = strtok(s, " "), *k;
    int ok = 1;
    if (!verb) return 1;
    if (!strcmp(verb, "wait")) {
        k = strtok(NULL, " ");
        sleep_ms(k ? atoi(k) : 0);
        return 1;
    }
    if (!strcmp(verb, "tap")) {
        k = strtok(NULL, " ");
        if (!k || !press(k, 1) || !report()) return 0;
        sleep_ms(60);
        return press(k, 0) && report();
    }
    if (strcmp(verb, "down") && strcmp(verb, "up")) {
        fprintf(stderr, "unknown step: %s\n", verb);
        return 0;
    }
    while ((k = strtok(NULL, " ")) != NULL)
        ok &= press(k, verb[0] == 'd');
    return ok && report();
}

int main(int argc, char **argv)
{
    struct uhid_event ev;
    int i, ok = 1;
    fd = open("/dev/uhid", O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        fprintf(stderr, "/dev/uhid: %s\n", strerror(errno));
        return 1;
    }
    memset(&ev, 0, sizeof ev);
    ev.type = UHID_CREATE2;
    strcpy((char *)ev.u.create2.name, "ssi263 test keyboard");
    ev.u.create2.rd_size = sizeof DESCRIPTOR;
    ev.u.create2.bus = BUS_USB;
    ev.u.create2.vendor = 0x1209;                /* pid.codes' test range */
    ev.u.create2.product = 0x0001;
    memcpy(ev.u.create2.rd_data, DESCRIPTOR, sizeof DESCRIPTOR);
    if (!send_event(&ev))
        return 1;
    for (i = 1; i < argc && ok; i++) {
        char buf[256];
        snprintf(buf, sizeof buf, "%s", argv[i]);
        ok = step(buf);
    }
    memset(keys, 0, sizeof keys);
    mods = 0;
    report();
    sleep_ms(200);
    memset(&ev, 0, sizeof ev);
    ev.type = UHID_DESTROY;
    send_event(&ev);
    close(fd);
    return ok ? 0 : 1;
}

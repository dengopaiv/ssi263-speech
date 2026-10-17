/* make_state.c -- a unit's factory state from its firmware alone, as the emulator starts it the first time.
 *
 *   make_state FIRMWARE english|spanish|german|italian|french OUT
 *
 * The unit is powered on and keyed through the recipe (../../csrc/blazie/bl_state.h: english is the three power-ons
 * that made bl2_2003_warm.state, and fits the Braille 'n Speak 2000's English and Slovak; spanish the Spanish
 * Braille Lite's reset), and its memory written to OUT.  Then it says which unit the firmware is for and the state's
 * sha256.  The Braille 'n Speak 2000's states, kept beside its firmware (firmware/blazie/bns2000/, never in git):
 *
 *   make_state firmware/blazie/bns2000/BS03ENG.BNS english firmware/blazie/bns2000/bs03eng_fresh.state
 *   make_state firmware/blazie/bns2000/BS2SLL.BNS english firmware/blazie/bns2000/bs2sll_fresh.state
 *
 * Blazie's September 2000 German and Italian Braille Lite 2000 (firmware/blazie/german/, italian/, never in git):
 *
 *   make_state firmware/blazie/german/Lite2000.BNS german firmware/blazie/german/lite2000_de_fresh.state
 *   make_state firmware/blazie/italian/Lite2000.BNS italian firmware/blazie/italian/lite2000_it_fresh.state
 *
 * The Braille 'n Speak 640's (firmware/blazie/bns640/, never in git; the Polish answers t):
 *
 *   make_state firmware/blazie/bns640/june2003/BSPENG.BNS english firmware/blazie/bns640/june2003/bspeng_fresh.state
 *   make_state firmware/blazie/bns640/issue15/BSPENG.BNS english firmware/blazie/bns640/issue15/bspeng_2000_fresh.state
 *   make_state firmware/blazie/bns640/issue15/bsppla.bns yes=t firmware/blazie/bns640/issue15/bsppla_fresh.state
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../csrc/blazie/bl_board.h"
#include "../../csrc/blazie/bl_firmware.h"
#include "../../csrc/blazie/bl_state.h"

int main(int argc, char **argv)
{
    char err[256];
    int language, model;
    bl_unit *u;
    static const char *names[] = {"english", "spanish", "german", "italian", "french"};
    static const int ids[] = {BLV_STATE_ENGLISH, BLV_STATE_SPANISH, BLV_STATE_GERMAN, BLV_STATE_ITALIAN,
                              BLV_STATE_FRENCH};
    /* yes=LETTER: the English recipe answered with that letter (a-z in computer braille, as the unit takes it) */
    static const unsigned char letter[26] = {0x01, 0x03, 0x09, 0x19, 0x11, 0x0B, 0x1B, 0x13, 0x0A, 0x1A, 0x05, 0x07,
                                             0x0D, 0x1D, 0x15, 0x0F, 0x1F, 0x17, 0x0E, 0x1E, 0x25, 0x27, 0x3A, 0x2D,
                                             0x3D, 0x35};
    int k, yes = -1, shape = BLV_SHAPE_ENGLISH;
    language = -1;
    for (k = 0; argc == 4 && k < 5; k++)
        if (!strcmp(argv[2], names[k]))
            language = ids[k];
    /* yes=LETTER: the English recipe's shape; slow=LETTER: the Spanish recipe's (bl_state.h BLV_SHAPE_*) */
    if (argc == 4 && (!strncmp(argv[2], "yes=", 4) || !strncmp(argv[2], "slow=", 5))) {
        const char *v = strchr(argv[2], '=') + 1;
        if (v[0] >= 'a' && v[0] <= 'z' && !v[1])
            yes = letter[v[0] - 'a'];
        shape = argv[2][0] == 's' ? BLV_SHAPE_SLOW : BLV_SHAPE_ENGLISH;
    }
    if (language < 0 && yes < 0) {
        fprintf(stderr, "usage: make_state FIRMWARE english|spanish|german|italian|french|yes=L|slow=L OUT\n");
        return 2;
    }
    u = bl_create(argv[1], NULL, 20.0, NULL, NULL, 0, err, sizeof err);
    if (!u) {
        fprintf(stderr, "make_state: %s\n", err);
        return 1;
    }
    model = bl_model(u);
    bl_destroy(u);
    if (!(yes >= 0 ? blv_make_state_yes(argv[1], shape, (unsigned char)yes, argv[3], NULL, NULL, err, sizeof err)
                   : blv_make_state(argv[1], language, argv[3], NULL, NULL, err, sizeof err))) {
        fprintf(stderr, "make_state: %s\n", err);
        return 1;
    }
    {
        FILE *f = fopen(argv[3], "rb");
        unsigned char *data, d[32];
        long n = -1;
        int k;
        if (f && fseek(f, 0, SEEK_END) == 0)
            n = ftell(f);
        data = n > 0 ? (unsigned char *)malloc((size_t)n) : NULL;
        if (!f || !data || fseek(f, 0, SEEK_SET) != 0 || fread(data, 1, (size_t)n, f) != (size_t)n) {
            fprintf(stderr, "make_state: cannot read back %s\n", argv[3]);
            return 1;
        }
        fclose(f);
        blv_sha256(data, n, d);
        free(data);
        printf("%s: a %s state, %ld bytes, sha256 ", argv[3], model == BL_MODEL_BNS2000 ? "Braille 'n Speak 2000"
               : model == BL_MODEL_BNS640 ? "Braille 'n Speak 640" : "Braille Lite 2000", n);
        for (k = 0; k < 32; k++)
            printf("%02x", d[k]);
        printf("\n");
    }
    return 0;
}

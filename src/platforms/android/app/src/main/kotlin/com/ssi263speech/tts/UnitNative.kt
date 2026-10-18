// Raw JNI binding to the Braille Lite unit screen's unit (cpp/ssa_unit_jni.c, on cpp/ssa_unit.c): one Blazie unit
// running in real time on the firmware imported for the voices.  A unit is a handle; ssa_unit's own lock serialises
// every call, so the sound thread and the keys may call it at once.
package com.ssi263speech.tts

object UnitNative {
    init { SsiNative.load() }

    /** A unit the data folder can run: its files' names in `codepage` (850, or 852 for the Slovak unit). */
    data class Unit(val key: String, val name: String, val typeNSpeak: Boolean, val saved: String, val codepage: Int)

    fun units(dataDir: String): List<Unit> = (nativeUnitList(dataDir) ?: emptyArray()).map { row ->
        val c = row.split('\t')
        Unit(c[0], c[1], c[2] == "1", c[3], c[4].toInt())
    }

    /** "Load programs and files into flash" on a switched-off unit's saved memory: "1\tadded\treplaced", "-1\tnames
     * it has already (one a line)" or "0\tthe reason".  times and dates as FAT keeps them. */
    external fun nativeUnitAddFiles(state: String, codepage: Int, names: Array<String>, datas: Array<ByteArray>,
                                    times: IntArray, dates: IntArray, replace: Boolean): String

    const val RATE = 22050

    external fun nativeUnitList(dataDir: String): Array<String>?
    /** Starts the unit (its memory in savedDir, made the first time): a handle, or 0 (nativeUnitError says why). A
     * release unit's first start makes its state first, which takes a while: nativeUnitProgress says how far. */
    external fun nativeUnitStart(dataDir: String, key: String, savedDir: String, rate: Int, idle: Int): Long
    external fun nativeUnitError(): String
    external fun nativeUnitProgress(): Double
    /** Saves it and frees it. */
    external fun nativeUnitStop(h: Long): Boolean
    external fun nativeUnitSave(h: Long): Boolean
    external fun nativeUnitRender(h: Long, pcm: ShortArray, n: Int)
    /** A key down or up: its scan code (0 for none), else the character it types.  True when the unit took it. */
    external fun nativeUnitKey(h: Long, scanCode: Int, char: Int, down: Boolean): Boolean
    external fun nativeUnitReleaseKeys(h: Long)
    /** The display as Unicode braille; "" for a unit with no display. */
    external fun nativeUnitBraille(h: Long): String
    external fun nativeUnitKind(h: Long): Int
    external fun nativeUnitModel(h: Long): Int
    external fun nativeUnitVolume(h: Long, volume: Int)
    external fun nativeUnitQuick(h: Long, on: Boolean)
    /** Keys held as the unit is switched on, before its first render (emu_hold_at_start): one-handed mode's dot 6
     * (ONE_HAND_ON) or dot 3 (ONE_HAND_OFF). */
    external fun nativeUnitHoldAtStart(h: Long, bits: Int)
    const val ONE_HAND_ON = 0x20
    const val ONE_HAND_OFF = 0x04
    external fun nativeUnitFlashBusy(h: Long): Boolean
}

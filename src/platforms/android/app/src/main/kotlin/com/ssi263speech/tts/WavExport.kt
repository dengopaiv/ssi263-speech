// What the settings screen's "Export to WAV…" writes (no Android in it, so the JVM tests run it): the name the file
// picker suggests -- the voice's unit and the time, speakout-20261018-164533.wav (Tomi) -- and the 16-bit mono WAV
// itself, the preview's render as it is.  The preview's last-render.wav is written the same way.
package com.ssi263speech.tts

import java.io.OutputStream
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

object WavExport {
    // The JVM tests' must-fail control: -Pssi263ImportBreak=export writes the header's lengths in the wrong byte order
    private val CONTROL = System.getProperty("ssi263.import.break") ?: ""
    private val STAMP = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss")
    private val LANGUAGE = Regex("[a-z]{2,3}")
    private val COUNTRY = Regex("[A-Z]{2}")

    /** "en-US-speakout" at 16:45:33 -> "speakout-20261018-164533.wav"; another language keeps its tag after the unit,
     * "de-DE-braillelite" -> "braillelite-de-...", "pt-BR-braillelite" -> "braillelite-pt-br-...". */
    fun fileName(voiceName: String, at: LocalDateTime): String {
        val parts = voiceName.split("-")
        var i = 0
        if (i < parts.size && LANGUAGE.matches(parts[i])) i++
        if (i in 1 until parts.size && COUNTRY.matches(parts[i])) i++
        if (i >= parts.size) i = 0                      // no unit after a tag: the name as it is
        val unit = parts.drop(i).joinToString("-")
        val language = parts.take(i).map { it.lowercase() }.distinct()
        val tag = if (language.firstOrNull() ?: "en" == "en") "" else "-" + language.joinToString("-")
        return "$unit$tag-${at.format(STAMP)}.wav"
    }

    /** 16-bit little-endian mono PCM as a WAV at `rate` Hz. */
    fun write(out: OutputStream, pcm: ByteArray, rate: Int) {
        fun i32(v: Int) = out.write(if (CONTROL == "export")
            byteArrayOf((v shr 24).toByte(), (v shr 16).toByte(), (v shr 8).toByte(), v.toByte())
            else byteArrayOf(v.toByte(), (v shr 8).toByte(), (v shr 16).toByte(), (v shr 24).toByte()))
        fun i16(v: Int) = out.write(byteArrayOf(v.toByte(), (v shr 8).toByte()))
        out.write("RIFF".toByteArray()); i32(36 + pcm.size); out.write("WAVE".toByteArray())
        out.write("fmt ".toByteArray()); i32(16); i16(1); i16(1); i32(rate); i32(rate * 2); i16(2); i16(16)
        out.write("data".toByteArray()); i32(pcm.size)
        out.write(pcm)
    }
}

package com.ssi263speech.tts

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.time.LocalDateTime

/** "Export to WAV…" (WavExport.kt): the name the save dialog suggests, and the file read back as a WAV reader would.
 * The control, -Pssi263ImportBreak=export, writes the header's lengths in the wrong byte order: the WAV case must FAIL. */
class WavExportTest {
    private val at = LocalDateTime.of(2026, 10, 18, 16, 45, 33)

    @Test fun theNameIsTheUnitAndTheTime() {
        assertEquals("speakout-20261018-164533.wav", WavExport.fileName("en-US-speakout", at))
        assertEquals("accentsa-20261018-164533.wav", WavExport.fileName("en-US-accentsa", at))
        assertEquals("mockingboard-early-20261018-164533.wav", WavExport.fileName("en-US-mockingboard-early", at))
        assertEquals("soundingboard-20261018-164533.wav", WavExport.fileName("en-US-soundingboard", at))
        // another language keeps its tag after the unit, once when the country only repeats it
        assertEquals("braillelite-de-20261018-164533.wav", WavExport.fileName("de-DE-braillelite", at))
        assertEquals("braillenspeak-sk-20261018-164533.wav", WavExport.fileName("sk-SK-braillenspeak", at))
        assertEquals("braillelite-pt-br-20261018-164533.wav", WavExport.fileName("pt-BR-braillelite", at))
        assertEquals("braillelite-ar-20261018-164533.wav", WavExport.fileName("ar-braillelite", at))
        // a name with no unit after its tag is kept whole
        assertEquals("en-US-20261018-164533.wav", WavExport.fileName("en-US", at))
    }

    @Test fun theFileIsAWavOfTheRender() {
        val pcm = ByteArray(2 * 1001) { (it * 7).toByte() }
        val out = ByteArrayOutputStream()
        WavExport.write(out, pcm, 22050)
        val wav = out.toByteArray()
        val b = ByteBuffer.wrap(wav).order(ByteOrder.LITTLE_ENDIAN)
        fun tag(at: Int) = String(wav, at, 4, Charsets.US_ASCII)
        assertEquals("RIFF", tag(0)); assertEquals(wav.size - 8, b.getInt(4)); assertEquals("WAVE", tag(8))
        assertEquals("fmt ", tag(12)); assertEquals(16, b.getInt(16))
        assertEquals(1, b.getShort(20).toInt())          // PCM
        assertEquals(1, b.getShort(22).toInt())          // mono
        assertEquals(22050, b.getInt(24)); assertEquals(44100, b.getInt(28))
        assertEquals(2, b.getShort(32).toInt()); assertEquals(16, b.getShort(34).toInt())
        assertEquals("data", tag(36)); assertEquals(pcm.size, b.getInt(40))
        assertArrayEquals(pcm, wav.copyOfRange(44, wav.size))
    }
}

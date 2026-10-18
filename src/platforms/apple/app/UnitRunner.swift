// UnitRunner.swift -- one Blazie unit running in real time for the Braille Lite unit tab: emu_unit.h's unit, its
// sound pulled by the audio engine at the unit's pace (emu_render, 22050 Hz), its keys pushed as they go down and up
// (chords.c: the chord is every key down since the first, sent when the last comes up; the keys held go to the unit as
// they move, so a chord held while it starts is read there), its two advance bars held as long as their keys are
// (emu_braille_bars), its display read as Unicode braille, and its memory saved when it is left.  The keys and the
// sound come from different threads: one lock serialises them, as the Windows and GTK shells' do.  MIT.

import AVFoundation
import Foundation
import os

final class UnitRunner {
    static let rate = 22050.0

    /// What the audio thread and the keys share, behind the lock.
    private final class Core: @unchecked Sendable {
        let lock = OSAllocatedUnfairLock()
        var unit: OpaquePointer?
        var chord = chord_state()
        var bars: Int32 = 0
        let pcm = UnsafeMutablePointer<Int16>.allocate(capacity: 1024)
        deinit { pcm.deallocate() }
    }

    private let core = Core()
    private let engine = AVAudioEngine()
    private var source: AVAudioSourceNode?
    private(set) var running: UnitCatalog.Entry?

    /// The Braille Lite's idle channel, as the GTK shell's Settings menu sets it (emu_set_idle): sound 0 silent, 1
    /// hiss, 2 whine, 3 as the unit (hiss at even volumes, whine at odd); keepOpen 0 off, 1 until the unit clicks off,
    /// 2 always; the pop when the channel opens and the click when it clicks off; the 10 Hz tick of the open channel.
    struct Idle: Equatable {
        var sound: Int32 = 3, keepOpen: Int32 = 1, popClick = true, tick = true
    }

    deinit { stop() }

    /// Starts the unit (the one running is saved and stopped first), with the double-speed upgrade fitted or not, and
    /// `hold`'s keys held for its first 2 s (emu_hold_at_start: one-handed mode's dot 6 or dot 3; 0 for none).
    /// Throws with the reason in words.
    func start(_ e: UnitCatalog.Entry, volume: Int, quick: Bool, doubleSpeed: Bool, idle: Idle,
               hold: Int32 = 0) throws {
        stop()
        let state = try UnitCatalog.prepare(e)
        var err = [CChar](repeating: 0, count: 300)
        guard let u = emu_create(e.unit.kind, UnitCatalog.firmware(e), state, UnitRunner.rate, idle.sound, &err,
                                 Int32(err.count)) else {
            throw UnitCatalog.Failure(message: "The \(e.name) would not start: \(String(cString: err)).")
        }
        set(u, idle)
        emu_set_volume(u, Int32(volume))
        emu_set_quick(u, quick ? 1 : 0)
        emu_set_double_speed(u, doubleSpeed ? 1 : 0)
        if hold != 0 { emu_hold_at_start(u, hold) }    // before its first render: held from its first instant
        core.lock.lock()
        core.unit = u
        chord_reset(&core.chord)
        core.bars = 0
        core.lock.unlock()
        running = e
        try startSound()
    }

    /// Saves the unit's memory and stops it.
    func stop() {
        engine.stop()
        if let s = source {
            engine.detach(s)
            source = nil
        }
        save()
        core.lock.lock()
        let u = core.unit
        core.unit = nil
        core.lock.unlock()
        if let u = u { emu_destroy(u) }
        running = nil
    }

    /// The unit's memory into its file: written beside it first, then put in place (as the Linux shells save), so a
    /// save cut short never loses the one before.  True when saved, or when there is nothing to save.
    @discardableResult
    func save() -> Bool {
        guard let e = running, let path = UnitCatalog.savedPath(e), let folder = UnitCatalog.savedFolder else {
            return true
        }
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let fresh = path.path + ".new"
        core.lock.lock()
        let saved = core.unit.map { emu_save($0, fresh) == 1 }
        core.lock.unlock()
        guard let ok = saved else { return true }        // no unit running
        return ok && rename(fresh, path.path) == 0
    }

    func setVolume(_ v: Int) { withUnit { emu_set_volume($0, Int32(v)) } }
    func setIdle(_ idle: Idle) { withUnit { set($0, idle) } }

    private func set(_ u: OpaquePointer, _ idle: Idle) {
        _ = emu_set_idle(u, idle.sound, idle.keepOpen, idle.popClick ? 1 : 0, idle.tick ? 1 : 0)
    }

    /// The unit is erasing or writing its file flash now (switching it off would lose the write).
    var writingFlash: Bool {
        var busy: Int32 = 0
        withUnit { busy = emu_flash($0, nil) }
        return busy != 0
    }
    func setQuick(_ on: Bool) { withUnit { emu_set_quick($0, on ? 1 : 0) } }
    func setDoubleSpeed(_ on: Bool) { withUnit { emu_set_double_speed($0, on ? 1 : 0) } }

    /// A key of the unit's keyboard (a chords.h bit: a dot, the space bar, an advance bar) went down or up.
    func key(_ bit: Int32, down: Bool) {
        withUnit { u in
            if down {
                chord_down(&core.chord, bit)
                emu_keys_down(u, core.chord.down)   // held: the unit sees them as it starts (i-chord: cold reset)
            } else {
                let chord = chord_up(&core.chord, bit)
                emu_keys_down(u, core.chord.down)
                if chord != 0 { emu_key(u, chord) }
            }
        }
    }

    /// The display's bars held from the braille field's keys (bit 0 forward, bit 1 back), as long as they are.
    func bars(_ bits: Int32) {
        withUnit { u in
            core.bars = bits
            emu_braille_bars(u, bits)
        }
    }

    /// Focus left the keyboard: a chord half pressed is dropped, the bars come up.
    func releaseKeys() {
        withUnit { u in
            chord_reset(&core.chord)
            emu_keys_down(u, 0)
            if core.bars != 0 {
                core.bars = 0
                emu_braille_bars(u, 0)
            }
        }
    }

    /// The display as the firmware last latched it, as Unicode braille (U+2800 + the dots); "" for a Braille Lite
    /// before its first latch, and for a unit with no display (the Braille 'n Speak).
    func braille() -> String {
        var cells = [UInt8](repeating: 0, count: Int(EMU_CELLS))
        var n: Int32 = 0
        withUnit { n = emu_braille($0, &cells, EMU_CELLS) }
        return String(String.UnicodeScalarView(cells.prefix(Int(n)).compactMap { Unicode.Scalar(0x2800 + UInt32($0)) }))
    }

    private func withUnit(_ body: (OpaquePointer) -> Void) {
        core.lock.lock()
        defer { core.lock.unlock() }
        if let u = core.unit { body(u) }
    }

    /// The unit's PCM, pulled by the audio engine at the sound card's pace.
    private func startSound() throws {
        #if os(iOS)
        // beside VoiceOver, never in its place
        try AVAudioSession.sharedInstance().setCategory(.playback, options: [.mixWithOthers])
        try AVAudioSession.sharedInstance().setActive(true)
        #endif
        guard let format = AVAudioFormat(standardFormatWithSampleRate: UnitRunner.rate, channels: 1) else { return }
        let core = self.core
        let node = AVAudioSourceNode(format: format) { _, _, frames, list -> OSStatus in
            let buffers = UnsafeMutableAudioBufferListPointer(list)
            guard let out = buffers[0].mData?.assumingMemoryBound(to: Float.self) else { return noErr }
            var done = 0
            core.lock.lock()
            while done < Int(frames) {
                let n = min(1024, Int(frames) - done)
                if let u = core.unit {
                    emu_render(u, core.pcm, Int32(n))
                    for i in 0..<n { out[done + i] = Float(core.pcm[i]) / 32768 }
                } else {
                    for i in 0..<n { out[done + i] = 0 }
                }
                done += n
            }
            core.lock.unlock()
            return noErr
        }
        source = node
        engine.attach(node)
        engine.connect(node, to: engine.mainMixerNode, format: format)
        try engine.start()
    }
}

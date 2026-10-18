// UnitModel.swift -- the Braille Lite unit tab's state: the units the imported firmware can run (UnitCatalog), the
// one running (UnitRunner) and its display, its sound's volume and the quick key response, and its memory saved when
// it is left or the app goes to the background.  The tab (UnitView) shows it.  MIT.

import SwiftUI
import os

private let log = Logger(subsystem: "com.ssi263speech.app", category: "unit")

@MainActor
final class UnitModel: ObservableObject {
    @Published private(set) var units: [UnitCatalog.Entry] = []
    @Published private(set) var running: String?            // the running unit's key
    @Published private(set) var cells = ""                  // its display, as Unicode braille
    @Published private(set) var busy = false
    @Published private(set) var status = ""
    @AppStorage("unit_last") var chosen = ""                // the app's own settings, not the App Group's
    @AppStorage("unit_volume") var volume = 100 { didSet { runner.setVolume(volume) } }
    @AppStorage("unit_quick") var quick = false { didSet { runner.setQuick(quick) } }
    // the Braille Lite's $99 double-speed chip fitted (off by default): its own switch then doubles its CPU
    @AppStorage("unit_double_speed") var doubleSpeed = false {
        didSet {
            runner.setDoubleSpeed(doubleSpeed)
            say(doubleSpeed ? Self.doubleSpeedNote : "Double-speed upgrade off.")
        }
    }
    // the idle channel, the GTK shell's defaults: as the unit, open until it clicks off, the pop and click, the tick
    @AppStorage("unit_idle") var idleSound = 3 { didSet { runner.setIdle(idle) } }
    @AppStorage("unit_keep_open") var keepOpen = 1 { didSet { runner.setIdle(idle) } }
    @AppStorage("unit_pop_click") var popClick = true { didSet { runner.setIdle(idle) } }
    @AppStorage("unit_tick") var tick = true { didSet { runner.setIdle(idle) } }
    @Published var replacing: [String] = []                // names the unit has already, while asking to replace
    @Published var asking = false
    @Published var report: String?                          // a load's outcome, shown until the next

    private var waiting: [UnitFiles.File] = []              // the files of the load being asked about

    private var idle: UnitRunner.Idle {
        UnitRunner.Idle(sound: Int32(idleSound), keepOpen: Int32(keepOpen), popClick: popClick, tick: tick)
    }

    /// The desktop's words, when the upgrade is said to be installed.
    static let doubleSpeedNote = "The double-speed upgrade is installed. To use it, switch it on in the unit: the " +
        "status menu, then + (dots 3-4-6), answered y. As on a real unit, programs that play sounds can misbehave " +
        "with it on: their tones can come out as a low rumble, and a game can stop the unit. Blazie's advice was to " +
        "switch double speed off for them. Restart the unit starts a stopped unit again."

    private let runner = UnitRunner()

    /// The running unit can be restarted one-handed or two-handed: not the Type 'n Speak (its manual has no such
    /// mode).
    var hasOneHandedMode: Bool { runner.running.map { $0.unit.kind != Int32(EMU_TYPE_N_SPEAK) } ?? false }
    private var timer: Timer?

    var actions: BrailleFieldActions {
        let r = runner
        return BrailleFieldActions(key: { r.key($0, down: $1) }, bars: { r.bars($0) }, released: { r.releaseKeys() })
    }

    func refresh() {
        units = UnitCatalog.list()
        if !units.contains(where: { $0.key == chosen }), let first = units.first { chosen = first.key }
    }

    /// The chosen unit started (the one running saved and stopped first); a release unit's first start makes its
    /// state, a few seconds, off the main thread.
    func start() {
        guard let e = units.first(where: { $0.key == chosen }), !busy else { return }
        busy = true
        var u = e.unit
        let first = emc_needs_factory(&u) != 0 && UnitCatalog.savedPath(e).map {
            !FileManager.default.fileExists(atPath: $0.path)
        } == true
        say(first ? "Setting up the \(e.name) for its first start; this takes a few seconds."
            : "Starting the \(e.name).")
        runner.stop()
        running = nil
        Task.detached {
            let prepared = Result { try UnitCatalog.prepare(e) }
            await MainActor.run {
                defer { self.busy = false }
                do {
                    _ = try prepared.get()
                    try self.runner.start(e, volume: self.volume, quick: self.quick, doubleSpeed: self.doubleSpeed,
                                          idle: self.idle)
                    self.running = e.key
                    self.say("The \(e.name) is running. The braille field has the keyboard.")
                    self.watch()
                } catch {
                    self.say(error.localizedDescription)
                }
            }
        }
    }

    /// The unit saved and stopped.
    func stop() {
        guard running != nil else { return }
        let name = runner.running?.name ?? "unit"
        runner.stop()
        running = nil
        cells = ""
        timer?.invalidate()
        say("The \(name) is switched off; its memory is kept.")
    }

    /// Restart the unit: what switching a real unit off and on does -- its memory saved (emu_save, which never asks
    /// the firmware, so a unit that has stopped answering is saved too), then started again from it with the settings
    /// applied again.  `hold`: one-handed mode's dot 6 (EMU_ONE_HAND_ON) or dot 3 (EMU_ONE_HAND_OFF) held as it starts;
    /// the firmware keeps the mode in its memory.  Not the factory reset.
    func restart(hold: Int32 = 0) {
        guard let e = runner.running, !busy else { return }
        if hold != 0 && !hasOneHandedMode { return }
        guard runner.save() else {
            say("Could not save the unit's memory, so it was not restarted.")
            return
        }
        runner.stop()
        do {
            try runner.start(e, volume: volume, quick: quick, doubleSpeed: doubleSpeed, idle: idle, hold: hold)
        } catch {
            running = nil
            cells = ""
            timer?.invalidate()
            say(error.localizedDescription)
            return
        }
        say(hold == 0 ? "The \(e.name) was restarted."
            : "The \(e.name) was restarted in \(hold == Int32(EMU_ONE_HAND_ON) ? "one" : "two")-handed mode.")
    }

    // ---- files into the unit's flash (UnitFiles) ---------------------------------------------------------------

    /// The files chosen in the picker: read now (they are the picker's to lend), then loaded.
    func load(_ urls: [URL]) {
        var files: [UnitFiles.File] = []
        for url in urls {
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            guard let data = try? Data(contentsOf: url) else {
                say("Could not read \(url.lastPathComponent). Nothing was loaded.")
                return
            }
            let date = (try? url.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate
            files.append(UnitFiles.File(name: url.lastPathComponent, data: data, modified: date ?? Date()))
        }
        load(files, replace: false)
    }

    /// The person's answer to "replace them?".
    func replace(_ yes: Bool) {
        let files = waiting
        waiting = []
        replacing = []
        if yes { load(files, replace: true) } else { say("Nothing was loaded. The unit's files are as they were.") }
    }

    /// The unit switched off (saved), the files into its saved memory, the unit switched on again -- the GTK shell's
    /// order.  Not while it writes its flash: that would be lost.
    private func load(_ files: [UnitFiles.File], replace: Bool) {
        guard let e = runner.running, !busy, let state = UnitCatalog.savedPath(e) else { return }
        if runner.writingFlash {
            say("The unit is writing its flash memory. Load the files when it has finished (when it is quiet).")
            return
        }
        guard runner.save() else {
            say("Could not save the unit's memory; nothing was changed.")
            return
        }
        busy = true
        runner.stop()
        let codepage = e.unit.codepage
        Task.detached {
            let outcome = UnitFiles.load(files, into: state.path, codepage: codepage, replace: replace)
            await MainActor.run {
                defer { self.busy = false }
                do {
                    try self.runner.start(e, volume: self.volume, quick: self.quick, doubleSpeed: self.doubleSpeed,
                                          idle: self.idle)
                } catch {
                    self.running = nil
                    self.cells = ""
                    self.say(error.localizedDescription)
                    return
                }
                switch outcome {
                case .exists(let names):
                    self.waiting = files
                    self.replacing = names
                    self.asking = true
                case .failed(let why):
                    self.say("Nothing was loaded: \(why) The unit was restarted with its files as they were.")
                case .loaded(let added, let replaced):
                    let n = files.count
                    self.report = "Loaded \(n) file\(n == 1 ? "" : "s") into flash: \(added) added, \(replaced) " +
                        "replaced. The unit was restarted. Run a program with o-chord x, its name, then e-chord; " +
                        "open a document with o-chord f o, its name, then e-chord."
                    self.say(self.report!)
                }
            }
        }
    }

    /// The unit's memory saved, as when it is left (the app going to the background).
    func save() {
        if !runner.save() { log.error("the unit's memory could not be saved") }
    }

    /// The display read 20 times a second, as the GTK shell reads it.
    private func watch() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self = self, self.running != nil else { return }
                let now = self.runner.braille()
                if now != self.cells { self.cells = now }
            }
        }
    }

    private func say(_ s: String) {
        status = s
        announce(s)
        log.notice("\(s, privacy: .public)")
    }
}

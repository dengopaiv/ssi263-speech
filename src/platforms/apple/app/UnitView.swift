// UnitView.swift -- the Blazie Engineering unit tab: run a Blazie unit on the firmware already imported for the voices
// (Setup's), from a Mac's or a Bluetooth keyboard -- the unit, its braille field, its sound's settings.  Built for
// VoiceOver first: the field is one element holding the display, the steps are announced.  MIT.

import SwiftUI
import UniformTypeIdentifiers

struct UnitView: View {
    @StateObject private var model = UnitModel()
    @Environment(\.scenePhase) private var phase
    @State private var picking = false

    /// The picker's kinds: the programs and documents a unit takes (UnitFiles.kinds), and any file.
    private static let types: [UTType] = UnitFiles.kinds.compactMap { UTType(filenameExtension: $0) } + [.item]

    var body: some View {
        Form {
            if model.units.isEmpty {
                Section {
                    Text("Import a Braille Lite's firmware in Setup first: this tab runs the units whose firmware " +
                         "you have imported.")
                }
            } else {
                Section {
                    // one unit at a time: the choice is dimmed while one runs, switching it off the only way on
                    Picker("Unit", selection: $model.chosen) {
                        ForEach(model.units) { Text($0.name).tag($0.key) }
                    }
                    .disabled(model.running != nil || model.busy)
                    if model.running == nil {
                        Button("Switch on") { model.start() }
                            .disabled(model.busy)
                    } else {
                        Button("Switch off") { model.stop() }
                            .disabled(model.busy)
                        // a power cycle, its files kept (never the factory reset); the one-handed ones hold a dot
                        // as it starts, as the manuals say
                        Button("Restart the unit (keeps its files)") { model.restart() }
                            .disabled(model.busy)
                        if model.hasOneHandedMode {
                            Button("Restart in one-handed mode (dot 6 held as it starts)") {
                                model.restart(hold: Int32(EMU_ONE_HAND_ON))
                            }
                            .disabled(model.busy)
                            Button("Restart in two-handed mode (dot 3 held as it starts)") {
                                model.restart(hold: Int32(EMU_ONE_HAND_OFF))
                            }
                            .disabled(model.busy)
                        }
                    }
                    if !model.status.isEmpty { Text(model.status) }
                } header: {
                    Text("Unit").accessibilityAddTraits(.isHeader)
                } footer: {
                    Text("The unit keeps its own memory, files and settings, saved when it is switched off or the " +
                         "app is left. Switch it off to choose another. Restart saves it and starts it again, as " +
                         "switching a real unit off and on, and works when it has stopped answering. One-handed " +
                         "mode, the Braille Lite's and the Braille 'n Speak's: the unit says so and keeps it until a " +
                         "two-handed restart.")
                }

                if model.running != nil {
                    Section {
                        BrailleField(text: model.cells, actions: model.actions)
                            .frame(minHeight: 48)
                    } header: {
                        Text("Braille display").accessibilityAddTraits(.isHeader)
                    } footer: {
                        Text(keysHelp)
                    }
                }

                if model.running != nil {
                    Section {
                        Button("Load programs and files into flash…") { picking = true }
                            .disabled(model.busy)
                        if let r = model.report { Text(r) }
                    } header: {
                        Text("Files").accessibilityAddTraits(.isHeader)
                    } footer: {
                        Text("Blazie programs (.bns), BASIC programs (.bas), text and braille files (.txt, .brl, " +
                             ".brf), one or several at once, into the unit's flash startup folder: the unit is " +
                             "switched off, the files added, and the unit switched on again. Its memory as it was " +
                             "is kept beside it.")
                    }
                }

                Section {
                    SettingSlider(title: "Volume", value: $model.volume, range: 0...100)
                    Toggle("Quick key response (faster than the real unit)", isOn: $model.quick)
                    Toggle("Double-speed upgrade installed (Braille Lite: its status menu's switch then works)",
                           isOn: $model.doubleSpeed)
                    Picker("Idle channel", selection: $model.idleSound) {
                        Text("As the unit (hiss at even volumes, whine at odd)").tag(3)
                        Text("Hiss").tag(1)
                        Text("Whine").tag(2)
                        Text("Silent").tag(0)
                    }
                    Picker("Keep the channel open", selection: $model.keepOpen) {
                        Text("Off (silent as soon as speech ends)").tag(0)
                        Text("Until the unit clicks off").tag(1)
                        Text("Always").tag(2)
                    }
                    Toggle("The pop when the channel opens, the click when it clicks off", isOn: $model.popClick)
                    Toggle("The 10 Hz tick of the open channel", isOn: $model.tick)
                } header: {
                    Text("Sound").accessibilityAddTraits(.isHeader)
                } footer: {
                    Text("The idle channel is the faint sound a real unit makes while its speech channel is open; " +
                         "the unit keeps it open for some seconds after it speaks, then clicks it off. The " +
                         "double-speed upgrade was a $99 option: with it installed, the unit's own switch (the " +
                         "status menu, then + (dots 3-4-6), answered y) doubles its speed.")
                }
            }
        }
        .navigationTitle("Blazie Engineering unit")
        .fileImporter(isPresented: $picking, allowedContentTypes: Self.types, allowsMultipleSelection: true) { r in
            if case .success(let urls) = r { model.load(urls) }
        }
        .confirmationDialog("Replace the unit's files?", isPresented: $model.asking, titleVisibility: .visible) {
            Button("Replace") { model.replace(true) }
            Button("Cancel", role: .cancel) { model.replace(false) }
        } message: {
            Text("The unit has files of these names already: \(model.replacing.joined(separator: ", ")). Replace " +
                 "them (each rewritten where it is)? Cancel loads nothing.")
        }
        .onAppear { model.refresh() }
        .onChange(of: phase) { p in if p != .active { model.save() } }
    }

    private var keysHelp: String {
        var s = "With the braille display field focused: F, D, S, J, K and L are dots 1 to 6, with the space bar; " +
            "semicolon and A are the advance and back bars. Alt+Shift+Right and Left hold the display's bars."
        #if os(iOS)
        s += " With VoiceOver, turn Quick Nav off (Left and Right arrows together) so the keys reach the unit."
        #endif
        return s
    }
}

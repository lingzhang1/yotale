import SwiftUI
import SwiftData

// R4-A.1 — Auto Backup settings (account-scoped). Lives as a sheet opened from the Moments Library (and later
// Settings). Default OFF; enabling is a one-time explicit opt-in with a disclosure; Wi-Fi-only by default with
// a separate cellular opt-in; and a one-time choice to also back up EXISTING local-only Moments (with a clear
// explanation that doing so associates them with THIS account and removes them from other accounts' libraries
// on this device). Never silently claims the shared local library.
struct AutoBackupSettingsView: View {
    @Environment(\.modelContext) private var context
    @Environment(\.dismiss) private var dismiss
    @Environment(AuthStore.self) private var auth

    /// Called when the user chooses to back up existing local-only Moments, so the host can enroll + drain.
    var onBackUpExisting: () -> Void

    @State private var enabled = false
    @State private var allowCellular = false
    @State private var showEnableDisclosure = false
    @State private var showExistingChoice = false

    private var store: AutoBackupStore { AutoBackupStore(context: context) }
    private var account: String? { auth.storyUserId }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Toggle("Auto Back Up My Moments", isOn: Binding(
                        get: { enabled },
                        set: { newValue in
                            if newValue && !enabled { showEnableDisclosure = true }   // one-time opt-in
                            else { setEnabled(newValue) }
                        }))
                    .tint(StoryTheme.gold)
                } footer: {
                    Text("When on, your Moments on this phone — the ones you already have and new ones you add while signed in — are backed up to your YoTale account. Your originals always stay on this iPhone — nothing is deleted.")
                }

                if enabled {
                    Section {
                        Toggle("Use Cellular Data", isOn: Binding(
                            get: { allowCellular },
                            set: { setAllowCellular($0) }))
                        .tint(StoryTheme.gold)
                    } footer: {
                        Text(allowCellular
                             ? "Uploads can use Wi-Fi or cellular data."
                             : "Uploads happen on Wi-Fi only. Moments wait until you're on Wi-Fi.")
                    }

                    Section {
                        Button("Back Up Moments Not Yet Backed Up…") { showExistingChoice = true }
                            .foregroundStyle(StoryTheme.gold)
                    } footer: {
                        Text("Turning Auto Backup on already does this. Use it again if some Moments still aren't backed up.")
                    }
                }
            }
            .navigationTitle("Auto Backup")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .onAppear(perform: load)
            // One-time opt-in disclosure. Turning Auto Backup ON also backs up the Moments already on this phone
            // that are not backed up yet (owner decision 2026-11-11), so the warning covers both.
            .confirmationDialog("Turn on Auto Backup?", isPresented: $showEnableDisclosure, titleVisibility: .visible) {
                Button("Turn On") {
                    setEnabled(true)
                    store.markExistingChoiceMade(for: account ?? "")
                    onBackUpExisting()
                }
                Button("Cancel", role: .cancel) { }
            } message: {
                Text("Your Moments on this phone that aren't backed up yet, and new Moments you add while signed in, will be uploaded privately to your YoTale account so they're safe if you lose this phone. Backing up a Moment associates it with this account. Originals stay on this device — nothing is deleted. Wi-Fi only unless you enable cellular. Only you can access your backups.")
            }
            // Re-run for Moments that are still not backed up (e.g. Auto Backup was already on, or an upload failed).
            .confirmationDialog("Back up Moments not yet backed up?", isPresented: $showExistingChoice, titleVisibility: .visible) {
                Button("Back Up Now") {
                    store.markExistingChoiceMade(for: account ?? "")
                    onBackUpExisting()
                }
                Button("Cancel", role: .cancel) { }
            } message: {
                Text("Backing up an existing Moment associates it with THIS account and removes it from other accounts' Moments libraries on this phone.")
            }
        }
    }

    private func load() {
        guard let a = account, let s = store.setting(for: a) else { enabled = false; allowCellular = false; return }
        enabled = s.enabled; allowCellular = s.allowCellular
    }
    private func setEnabled(_ v: Bool) {
        guard let a = account else { return }
        store.setEnabled(v, for: a); enabled = v
    }
    private func setAllowCellular(_ v: Bool) {
        guard let a = account else { return }
        store.setAllowCellular(v, for: a); allowCellular = v
    }
}

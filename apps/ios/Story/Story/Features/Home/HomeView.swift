import SwiftUI
import SwiftData

// Home — Figma MVP V0.2.2 (Capture Anywhere). Hierarchy:
//   Primary:   Capture a Moment (opens the shared camera immediately) · Start a Story
//   Secondary: Moments (global library) · Stories (projects/films list)
// Dark cinematic styling preserved. The obsolete disabled "Create now" and
// "Use existing photos/videos" entries are removed (owner decision V0.2.2).
struct HomeView: View {
    @Environment(\.modelContext) private var context
    @Environment(AuthStore.self) private var auth
    @Environment(BillingStore.self) private var billing
    @Environment(AppLanguageStore.self) private var languageStore
    @Query private var stories: [StoryModel]
    @Query private var moments: [MomentModel]

    @State private var showCapture = false
    @State private var showStories = false
    @State private var confirmSignOut = false
    @State private var showSignIn = false   // Home-header direct sign-in sheet (no gated action required)
    @State private var showPlus = false     // Billing V1 / B3: YoTale Plus subscription screen
    @State private var showDeleteAccount = false   // Account deletion (D5)

    // R1 account isolation: the @Query is unscoped (SwiftData predicates can't close over runtime auth state),
    // so we filter in memory through the CENTRALIZED AccountScope rules. SwiftUI re-renders this view when
    // `auth.storyUserId` changes, so switching accounts (or signing out) refreshes both the counts and lists
    // with no stale visibility.
    private var visibleStories: [StoryModel] { stories.visible(to: auth.storyUserId) }
    private var visibleMoments: [MomentModel] { moments.visible(to: auth.storyUserId) }

    // Active Stories first (most recent first), then completed below.
    private var sortedStories: [StoryModel] {
        visibleStories.sorted { a, b in
            if a.status != b.status { return a.status == .active }
            return a.createdAt > b.createdAt
        }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    header

                    // ── Primary 1: Capture a Moment — opens the shared camera immediately,
                    //    no Story / CreativeIntent / AI call required to open it.
                    Button { showCapture = true } label: {
                        StoryImageCard(image: "ph_city", eyebrow: "Capture",
                                       title: "Capture a Moment",
                                       sub: "Capture something worth remembering. Get an AI shot idea whenever you want.",
                                       icon: "camera.fill")
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .padding(.bottom, 14)

                    // ── Primary 2: Start a Story — existing C1 flow, unchanged.
                    NavigationLink { CreativeDirectionView() } label: {
                        StoryImageCard(image: "ph_alpine", eyebrow: "Create",
                                       title: "Start a Story",
                                       sub: "Collect moments, tell your story, and create a film.",
                                       icon: "film.fill")
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .padding(.bottom, 14)

                    // ── Secondary destinations: Moments · Stories
                    HStack(spacing: 12) {
                        NavigationLink { MomentsLibraryView() } label: {
                            secondaryCard(icon: "photo.on.rectangle", count: visibleMoments.count,
                                          title: "Moments", sub: "Your captured memories")
                        }
                        .buttonStyle(.plain)

                        Button { showStories = true } label: {
                            secondaryCard(icon: "film", count: visibleStories.count,
                                          title: "Stories", sub: "Your projects and films")
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 20)
                .padding(.bottom, 40)
            }
            .storyBackground()
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(isPresented: $showStories) { StoriesListView() }
        }
        .tint(StoryTheme.gold)
        .fullScreenCover(isPresented: $showCapture) {
            // Standalone capture — NO Story association, library-only. The scene-only
            // AI intent carries no prior Story (no stale-context leak).
            ContinuousCaptureView(captureContext: .standalone(direction: nil))
        }
    }

    private var header: some View {
        HStack {
            StoryEyebrow(text: "YoTale")
            Spacer()
            languageMenu
            // Account affordance in the Home header — the ONLY entry point to sign in WITHOUT first triggering a
            // gated AI action (Start a Story / music search / capture AI). Beta testers can sign in here to see
            // their account's Stories and to (re-)test the OTP flow.
            //   • Signed in  -> a menu: how the user is signed in (provider, or the email for code sign-in; read
            //                   from the id token as a display hint only), YoTale Plus with its status, Sign Out,
            //                   and Delete Account in its own section.
            //   • Signed out -> a "Sign In" button that presents the shared SignInView as a sheet. No Story is
            //                   created and no AI is triggered; local content stays visible either way.
            if auth.isSignedIn {
                Menu {
                    Section {
                        Text(signedInDescription)
                        Button { showPlus = true } label: {
                            Text("YoTale Plus")
                            if let plusStatus { Text(plusStatus) }
                            Image(systemName: "sparkles")
                        }
                        // Not destructive: signing out keeps everything on this iPhone.
                        Button { confirmSignOut = true } label: {
                            Label("Sign Out", systemImage: "rectangle.portrait.and.arrow.right")
                        }
                    }
                    if AccountDeletionAvailability.offered {
                        // Own section, so it is separated from Sign Out by a divider.
                        Section {
                            Button(role: .destructive) { showDeleteAccount = true } label: {
                                Label { Text(L10n.t("Delete Account")) } icon: { Self.redSymbol("trash") }
                            }
                        }
                    }
                } label: {
                    // Filled when signed in (the signed-out state is the labelled "Sign In" button below).
                    Image(systemName: "person.crop.circle.fill")
                        .font(.system(size: 20))
                        .foregroundStyle(StoryTheme.cream.opacity(0.7))
                }
                .accessibilityLabel(Text(L10n.t("Account")))
                .accessibilityValue(Text(signedInDescription))
            } else {
                Button { showSignIn = true } label: {
                    Label("Sign In", systemImage: "person.crop.circle")
                        .font(StoryTheme.body(14))
                        .foregroundStyle(StoryTheme.gold)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.top, 32).padding(.bottom, 22)
        .confirmationDialog(L10n.t("Sign out of YoTale?"), isPresented: $confirmSignOut, titleVisibility: .visible) {
            Button("Sign Out") { billing.reset(); auth.signOut() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text(L10n.t("Your Moments and Stories stay on this iPhone. Sign in again to use YoTale's AI features."))
        }
        .sheet(isPresented: $showPlus) { PlusSubscriptionView() }
        .sheet(isPresented: $showDeleteAccount) { DeleteAccountView() }
        .sheet(isPresented: $showSignIn) {
            // Direct sign-in from Home: no pending action to resume — dismiss on success or cancel. On success,
            // AuthStore resolves the canonical story_user_id (R1.1) and the Home lists re-scope to the account.
            SignInView(auth: auth,
                       onSignedIn: { showSignIn = false },
                       onCancel: { showSignIn = false })
        }
    }

    /// How the user is signed in, for the account menu. Display hint from the UNVERIFIED id token; never identity.
    private var signedInDescription: String {
        let hint = auth.accountHint
        switch hint?.federatedProvider {
        case StoryAuthConfig.appleProviderName?: return L10n.t("Signed in with Apple")
        case StoryAuthConfig.googleProviderName?: return L10n.t("Signed in with Google")
        default:
            if let email = hint?.email, !email.isEmpty { return L10n.t("Signed in as \(email)") }
            return L10n.t("Signed in")
        }
    }

    /// YoTale Plus status on the menu row; nil while the entitlement is unknown (not loaded or failed).
    private var plusStatus: String? {
        if billing.isPlus { return L10n.t("Subscribed") }
        if billing.canOfferSubscribe { return L10n.t("Subscribe") }
        return nil
    }

    /// A menu icon that keeps its own colour: menus render SF Symbols with the app's gold tint, which made the
    /// destructive Delete Account icon gold next to red text.
    static func redSymbol(_ name: String) -> Image {
        #if canImport(UIKit)
        if let ui = UIImage(systemName: name)?.withTintColor(.systemRed, renderingMode: .alwaysOriginal) {
            return Image(uiImage: ui)
        }
        #endif
        return Image(systemName: name)
    }

    // Language picker — ALWAYS visible (signed in or out). Endonyms are never translated.
    private var languageMenu: some View {
        @Bindable var store = languageStore
        return Menu {
            Picker("Language", selection: $store.preference) {
                ForEach(AppLanguage.allCases) { lang in
                    if let name = lang.endonym {
                        Text(verbatim: name).tag(lang)
                    } else {
                        Text("Follow iPhone language").tag(lang)
                    }
                }
            }
        } label: {
            Image(systemName: "globe")
                .font(.system(size: 20))
                .foregroundStyle(StoryTheme.cream.opacity(0.7))
                .padding(.trailing, 10)
        }
        .accessibilityLabel("Language")
    }

    // Compact secondary destination card (icon + count row, title, sub).
    private func secondaryCard(icon: String, count: Int, title: String, sub: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Image(systemName: icon)
                    .font(.system(size: 18)).foregroundStyle(StoryTheme.cream.opacity(0.7))
                Spacer()
                Text("\(count)")
                    .font(StoryTheme.body(15)).foregroundStyle(StoryTheme.cream.opacity(0.5))
            }
            .padding(.bottom, 18)
            Text(LocalizedStringKey(title)).font(StoryTheme.display(18)).foregroundStyle(StoryTheme.cream)
            Text(LocalizedStringKey(sub)).font(StoryTheme.body(12)).foregroundStyle(StoryTheme.cream.opacity(0.45))
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
        .background(StoryTheme.cream.opacity(0.03))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(StoryTheme.cream.opacity(0.08), lineWidth: 1))
        .contentShape(Rectangle())
    }
}

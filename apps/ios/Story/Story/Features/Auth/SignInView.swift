import SwiftUI

/// Passwordless email sign-up AND sign-in in ONE screen (TestFlight self-signup, Option A): enter email →
/// get a code → enter it → you're in. A brand-new email self-registers (Cognito SignUp + ConfirmSignUp); a
/// returning email signs in (EMAIL_OTP). The visual journey is identical; the client runs the correct Cognito
/// operation behind the scenes. No passwords, no invite codes, no separate registration screen.
struct SignInView: View {
    let auth: AuthStore
    var onSignedIn: () -> Void
    var onCancel: () -> Void

    private enum Step { case email, code }
    @State private var step: Step = .email
    @State private var email = ""
    @State private var code = ""
    @State private var challenge: OTPChallenge?
    @State private var busy = false
    @State private var error: String?
    @State private var cooldown = OTPCooldown()
    @State private var cooldownLeft = 0
    @State private var timer: Timer?

    var body: some View {
        // Top-aligned in a scroll view: the sheet no longer floats the form in the middle of an empty screen,
        // and the keyboard can't cover the buttons on small phones.
        ScrollView {
            VStack(spacing: 24) {
                header

                switch step {
                case .email:
                    // One-tap providers first, then the email code path under an "or" divider.
                    if StoryAuthConfig.appleSignInAvailable {
                        VStack(spacing: 12) {
                            AppleSignInButton(enabled: !busy) { Task { await appleSignIn() } }
                            if StoryAuthConfig.googleSignInAvailable {
                                GoogleSignInButton(enabled: !busy) { Task { await googleSignIn() } }
                            }
                        }
                        orDivider
                    } else {
                        Label("Apple sign-in unavailable in this build", systemImage: "applelogo")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                    emailStep
                case .code:
                    codeStep
                }

                if let error { Text(error).font(.footnote).foregroundStyle(.red).multilineTextAlignment(.center) }
                Button("Not now", action: onCancel).font(.subheadline)
            }
            .padding(.horizontal, StoryTheme.screenPadding)
            .padding(.top, 48).padding(.bottom, 24)
        }
        .scrollDismissesKeyboard(.interactively)
        .presentationDragIndicator(.visible)
        .onDisappear { timer?.invalidate() }
    }

    private var header: some View {
        VStack(spacing: 10) {
            Text(verbatim: "YoTale")
                .font(StoryTheme.display(36))
            Text("Sign in to use Story's AI")
                .font(.title3.weight(.semibold))
            Text("Your captured Moments and saved Stories stay on this device either way.")
                .font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }
        .padding(.bottom, 8)
    }

    private var orDivider: some View {
        HStack(spacing: 12) {
            Rectangle().fill(Color(.separator)).frame(height: 1)
            Text("Or use your email").font(.footnote).foregroundStyle(.secondary).fixedSize()
            Rectangle().fill(Color(.separator)).frame(height: 1)
        }
    }

    private var emailStep: some View {
        VStack(spacing: 12) {
            TextField("you@example.com", text: $email)
                .textContentType(.emailAddress).keyboardType(.emailAddress)
                .textInputAutocapitalization(.never).autocorrectionDisabled()
                .signInFieldStyle()
            Button { Task { await requestCode() } } label: {
                HStack { if busy { ProgressView() }; Text("Continue") }.frame(maxWidth: .infinity)
            }
            .signInPrimaryStyle()
            .disabled(busy || !AuthHelpers.isPlausibleEmail(email))
            Text("New here or returning — we'll email you a code. No password needed.")
                .font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }
    }

    private var codeStep: some View {
        VStack(spacing: 12) {
            Text("Enter the code sent to \(challenge?.maskedDestination ?? AuthHelpers.normalizeEmail(email))")
                .font(.subheadline).foregroundStyle(.secondary).multilineTextAlignment(.center)
            TextField("123456", text: $code)
                .keyboardType(.numberPad).multilineTextAlignment(.center)
                .textContentType(.oneTimeCode)
                .signInFieldStyle()
            Button { Task { await verify() } } label: {
                HStack { if busy { ProgressView() }; Text("Verify") }.frame(maxWidth: .infinity)
            }
            .signInPrimaryStyle().disabled(busy || code.count < 4)
            Button(cooldownLeft > 0 ? L10n.t("Resend in \(cooldownLeft)s") : L10n.t("Resend code")) {
                Task { await resend() }
            }
            .font(.subheadline).disabled(busy || cooldownLeft > 0)
            Text("The code can take a minute or two to arrive. Check your spam folder if you don't see it.")
                .font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }
    }

    // ---- actions ----
    private func requestCode() async {
        guard cooldown.canRequest() else { startCooldownTimer(); return }
        error = nil; busy = true; defer { busy = false }
        do {
            challenge = try await auth.startEmailAuth(email: email)
            step = .code
            startCooldownTimer()
        } catch { self.error = (error as? LocalizedError)?.errorDescription ?? L10n.t("Couldn't send a code.") }
    }

    private func resend() async {
        guard let current = challenge, cooldown.canRequest() else { startCooldownTimer(); return }
        error = nil; busy = true; defer { busy = false }
        do {
            challenge = try await auth.resendCode(for: current)
            startCooldownTimer()
        } catch { self.error = (error as? LocalizedError)?.errorDescription ?? L10n.t("Couldn't resend the code.") }
    }

    private func verify() async {
        guard let challenge else { return }
        error = nil; busy = true; defer { busy = false }
        do {
            try await auth.verifyCode(code, challenge: challenge)
            onSignedIn()
        } catch CognitoAuthError.badCode {
            code = ""; error = CognitoAuthError.badCode.errorDescription
        } catch CognitoAuthError.expiredCode {
            // The code (and this challenge) are dead — send the user back to request a fresh one.
            code = ""; self.challenge = nil; step = .email
            error = CognitoAuthError.expiredCode.errorDescription
        } catch CognitoAuthError.tooManyAttempts {
            code = ""; self.challenge = nil; step = .email
            error = CognitoAuthError.tooManyAttempts.errorDescription
        } catch CognitoAuthError.noChallengeSession {
            // New account was CONFIRMED but Cognito couldn't auto-sign-in from the signup session; a fresh
            // sign-in code was just sent. Keep the user on the code screen as an EXISTING-user challenge.
            code = ""
            self.challenge = OTPChallenge(session: "", email: AuthHelpers.normalizeEmail(email),
                                          maskedDestination: challenge.maskedDestination, kind: .signIn)
            Task { await requestFreshSignInCode() }
            error = L10n.t("Almost there — enter the new code we just emailed you.")
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? L10n.t("That code didn't work.")
        }
    }

    /// Replace the placeholder post-confirm challenge with a real EMAIL_OTP sign-in challenge (carries the
    /// Cognito Session needed to verify). Used only on the rare ConfirmSignUp-session fallback.
    private func requestFreshSignInCode() async {
        do { challenge = try await auth.startEmailAuth(email: email) }
        catch { self.error = (error as? LocalizedError)?.errorDescription ?? L10n.t("Couldn't send a new code.") }
    }

    private func appleSignIn() async {
        error = nil; busy = true; defer { busy = false }
        do { try await auth.signInWithApple(); onSignedIn() }
        catch { self.error = (error as? LocalizedError)?.errorDescription ?? L10n.t("Apple sign-in failed.") }
    }

    private func googleSignIn() async {
        error = nil; busy = true; defer { busy = false }
        do { try await auth.signInWithGoogle(); onSignedIn() }
        catch { self.error = (error as? LocalizedError)?.errorDescription ?? L10n.t("Google sign-in failed.") }
    }

    private func startCooldownTimer() {
        timer?.invalidate()
        cooldownLeft = cooldown.secondsRemaining()
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { t in
            Task { @MainActor in
                cooldownLeft = max(0, cooldownLeft - 1)
                if cooldownLeft == 0 { t.invalidate() }
            }
        }
    }
}

// ---- shared sign-in controls ----
// Every control on this screen uses the same height and corner radius so the providers and the email path
// read as one set, and so Apple and Google get equal prominence (both brands' rules ask for that).
private enum SignInMetrics {
    static let height: CGFloat = 50
    static let cornerRadius: CGFloat = 12
}

private extension View {
    func signInFieldStyle() -> some View {
        padding(.horizontal, 14)
            .frame(height: SignInMetrics.height)
            .background(Color(.secondarySystemBackground),
                        in: RoundedRectangle(cornerRadius: SignInMetrics.cornerRadius))
            .overlay(RoundedRectangle(cornerRadius: SignInMetrics.cornerRadius)
                .strokeBorder(Color(.separator), lineWidth: 1))
    }

    func signInPrimaryStyle() -> some View {
        buttonStyle(.borderedProminent)
            .controlSize(.large)
            .buttonBorderShape(.roundedRectangle(radius: SignInMetrics.cornerRadius))
    }
}

/// Custom "Continue with Apple" button drawn to Apple's HIG for Sign in with Apple (black in light mode, white
/// in dark mode, Apple logo plus title, same height as the other buttons). The system
/// `ASAuthorizationAppleIDButton` was dropped because it titles itself in the PHONE's language and ignores the
/// app's own language setting, so a Chinese app showed an English button. SwiftUI's `SignInWithAppleButton` is
/// not an option either: it always starts the native Apple flow, which a Cognito User Pool cannot accept. The tap
/// runs `AuthStore.signInWithApple()` (Cognito hosted web flow).
private struct AppleSignInButton: View {
    var enabled: Bool
    var action: () -> Void
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let dark = colorScheme == .dark
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: "applelogo").font(.system(size: 19, weight: .medium))
                Text("Continue with Apple").font(.system(size: 17, weight: .semibold))
            }
            .foregroundStyle(dark ? Color.black : Color.white)
            .frame(maxWidth: .infinity, minHeight: SignInMetrics.height)
            .background(dark ? Color.white : Color.black,
                        in: RoundedRectangle(cornerRadius: SignInMetrics.cornerRadius))
            .contentShape(RoundedRectangle(cornerRadius: SignInMetrics.cornerRadius))
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .opacity(enabled ? 1 : 0.5)
    }
}

/// "Continue with Google" in Google's Light theme (fill #FFFFFF, 1 pt #747775 stroke, #1F1F1F text) with the
/// official standard-color "G" at its fixed 20 pt size, cropped from Google's signin-assets.zip
/// (Assets.xcassets/google_g). Google allows the title to be localized to the app's language.
private struct GoogleSignInButton: View {
    var enabled: Bool
    var action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image("google_g").resizable().frame(width: 20, height: 20).accessibilityHidden(true)
                Text("Continue with Google").font(.system(size: 17, weight: .medium))
            }
            .foregroundStyle(Color(hex: 0x1F1F1F))
            .frame(maxWidth: .infinity, minHeight: SignInMetrics.height)
            .background(Color.white, in: RoundedRectangle(cornerRadius: SignInMetrics.cornerRadius))
            .overlay(RoundedRectangle(cornerRadius: SignInMetrics.cornerRadius)
                .strokeBorder(Color(hex: 0x747775), lineWidth: 1))
            .contentShape(RoundedRectangle(cornerRadius: SignInMetrics.cornerRadius))
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .opacity(enabled ? 1 : 0.5)
    }
}

# 07 - Teacher: First-Time Login (Magic Link)

**Tool**: `gemini --yolo "/diagram '...'"`
**Generated**: 2026-03-19

## Prompt

```
Teacher First-Time Login - Magic Link Flow. User flow diagram.

Flow (top to bottom):
1. Teacher receives invite email from noreply@vigour.app - Welcome to Vigour Test
2. Opens email on phone → email shows invitation from school with Open Vigour Test button
3. Taps link → Decision: App installed?
4. If no → App Store/Play Store → Downloads and installs → Opens app
5. If yes → App opens via deep link
6. Welcome Screen with Vigour logo and school branding, Enter email to continue
7. Enters school email (e.g. jane@oakwood.edu.za) → Taps Continue
8. Decision: Email registered? If no → Not registered message with school admin contact. Try again or close.
9. If yes → 6-digit code sent to email (5 min expiry)
10. Code Entry Screen with 6 digit input and Resend option
11. Enters code → Decision: Code valid?
12. If wrong code → Invalid code, attempts remaining. Retry or Resend.
13. If expired → Request new code
14. If valid → JWT tokens issued (access 15min + refresh 7 days), stored in secure keychain
15. First-Time Setup screen: Welcome Mrs van Wyk, Your school: Oakwood Primary, Your classes: Grade 6A (28), Grade 6B (26)
16. Decision: Take the tour? Yes → guided walkthrough. Skip → Home Screen
17. Home Screen with classes, no sessions yet, Start your first session prompt

Clean modern mobile app flow style, rounded shapes for user actions, clear error paths in red.
```

## Regenerate

```bash
cd docs/architecture/diagrams
GEMINI_API_KEY="$NANOBANANA_GEMINI_API_KEY" gemini --yolo "/diagram 'Teacher First-Time Login - Magic Link Flow. User flow diagram.

Flow (top to bottom):
1. Teacher receives invite email from noreply@vigour.app - Welcome to Vigour Test
2. Opens email on phone → email shows invitation from school with Open Vigour Test button
3. Taps link → Decision: App installed?
4. If no → App Store/Play Store → Downloads and installs → Opens app
5. If yes → App opens via deep link
6. Welcome Screen with Vigour logo and school branding, Enter email to continue
7. Enters school email (e.g. jane@oakwood.edu.za) → Taps Continue
8. Decision: Email registered? If no → Not registered message with school admin contact. Try again or close.
9. If yes → 6-digit code sent to email (5 min expiry)
10. Code Entry Screen with 6 digit input and Resend option
11. Enters code → Decision: Code valid?
12. If wrong code → Invalid code, attempts remaining. Retry or Resend.
13. If expired → Request new code
14. If valid → JWT tokens issued (access 15min + refresh 7 days), stored in secure keychain
15. First-Time Setup screen: Welcome Mrs van Wyk, Your school: Oakwood Primary, Your classes: Grade 6A (28), Grade 6B (26)
16. Decision: Take the tour? Yes → guided walkthrough. Skip → Home Screen
17. Home Screen with classes, no sessions yet, Start your first session prompt

Clean modern mobile app flow style, rounded shapes for user actions, clear error paths in red.'"
```

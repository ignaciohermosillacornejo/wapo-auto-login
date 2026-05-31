# SPL → WaPo Login Flow (Stage 1 recon)

Captured 2026-05-30 via `playwright codegen --save-har` from a fresh Chromium profile.

## TL;DR

The "SPL → WaPo" flow has no SPL library-card login. The SPL resource page just links to a WaPo special-offers URL; WaPo's own sign-in plus the special-offers query string is what grants the entitlement.

**Net result:** we only need WaPo credentials — not SPL card + PIN.

## The flow

1. Direct URL (skips SPL page entirely — confirmed in the HAR; the SPL link is a static link to this URL):
   ```
   https://www.washingtonpost.com/subscribe/signin/special-offers/?s_oe=SPECIALOFFER_SEATTLEPL
   ```
2. If logged out: WaPo sign-in form appears in-page. Fill email, click sign-in button, fill password, click sign-in button.
3. After successful sign-in, the page fires `POST https://subscribe.washingtonpost.com/subscriptionapi/v2/subscriptions/special-offers` — a 200 response means the entitlement was minted (this is the activation signal — the "Your free trial has been activated!" email follows shortly).

## Selectors (from `recon/recorded.py`)

| Element | Selector |
|---|---|
| Email input | `page.get_by_role("textbox", name="Email address")` |
| Password input | `page.get_by_role("textbox", name="Password")` |
| Sign-in button | `[data-test-id="sign-in-btn"]` (same button is reused for both email-only and email+password screens) |

The sign-in is a two-step UI: enter email → click sign-in → password field appears → enter password → click sign-in.

## Success signature

**Primary**: wait for response from `https://subscribe.washingtonpost.com/subscriptionapi/v2/subscriptions/special-offers` with status 200. This is the entitlement-minting API; a 200 means success.

**Backup**: after the API call, the sign-in form is no longer visible. We can additionally wait for the email textbox to become detached.

## Idempotency probe

Since visiting the special-offers URL always re-mints the entitlement (per the SPL page's instruction: "Continued access requires you to use this link again and login with the same username and password you originally created"), the cheapest probe is just: visit the URL. If the persistent profile has valid WaPo cookies, the sign-in form will not appear and the API call still fires (idempotent re-mint).

So the script logic simplifies to:
1. Visit special-offers URL
2. If sign-in form is visible (logged out), perform sign-in
3. Wait for the entitlement API 200 response
4. Done

No separate probe URL needed.

## CAPTCHA observations

- **None observed** on this attempt.
- WaPo's sign-in is plain HTML form + XHR; no visible bot challenge.

**Decision gate: PROCEED with automation.**

If a CAPTCHA does appear on a future run, it would be at the sign-in step. The bot will time out waiting for the API response; debug artifacts will show the challenge.

## Other notes

- The sign-in is a popup window from the SPL page (`page.expect_popup`), but if we go to the special-offers URL directly, there's no popup.
- HAR captured 113 requests across the flow; most are tracking/analytics.
- The flow does NOT redirect to any external IdP (no BiblioCommons, EZproxy, OpenAthens, OCLC SSO). It's pure WaPo auth + a referral query string.

## Credentials needed

- `WAPO_EMAIL` — WaPo account email
- `WAPO_PASSWORD` — WaPo account password

**Removed from earlier spec assumptions:**
- ~~`SPL_CARD`~~ — not used
- ~~`SPL_PIN`~~ — not used

## Security note

The codegen output (`recon/recorded.py`) and HAR (`recon/network.har`) captured the WaPo password in plaintext. Both files are gitignored. The password should be rotated after this work is complete, since it was captured to disk during recon.

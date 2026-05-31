# WaPo Auto-Login via SPL — Design

**Date:** 2026-05-30
**Owner:** nach
**Status:** Spec — awaiting implementation

## Problem

Free Washington Post digital access via Seattle Public Library (SPL) is provisioned as a short-lived "free-trial"-class entitlement on a real `washingtonpost.com` account. The entitlement re-mints each time the user re-authenticates through SPL's library-card flow, then expires (observed cadence between activations: 9–39 days, consistent with a ~7-day grant renewed lazily on next use). Today, nach manually re-walks the SPL → WaPo login roughly weekly, which is annoying.

Goal: automate the re-authentication so it runs unattended on `seattle-server` on a schedule, with the user only intervening when something genuinely breaks (e.g., WaPo presents a CAPTCHA the bot cannot solve).

## Non-goals

- Sharing access with other people. This is single-user, personal automation of nach's own credentials.
- Scraping or redistributing WaPo content. Only the entitlement-refresh action is automated.
- Generalizing to other libraries or other newspapers.
- Building a service with a UI. CLI + log file only.

## Confirmed facts from prior research

Source: prior mailbox audit of `hermosillaignacio@gmail.com`.

- nach is a confirmed SPL patron (OverDrive hold notices in inbox).
- WaPo sends a recurring **"Your free trial has been activated!"** email from `updates@comms.mail.washingtonpost.com` with internal subject "Subscription Confirmation and Account Details". At least 10 such emails since 2025-10-19, with gaps of 9–39 days.
- Email body links to `https://www.washingtonpost.com/subscribe/signin?utm_source=email&utm_medium=free-trial&utm_campaign=sign-in`. The `utm_medium=free-trial` tag confirms the entitlement is a free-trial-class subscription on a real WaPo account.
- This is the **WaPo "access through your local library/university" partnership** — not PressReader. Web + native-app access.
- The durable credential is the SPL library login; the WaPo entitlement is a derivative re-minted on each library hand-off. **An automation that only refreshes WaPo cookies will eventually fail** — it must replay the library login end-to-end.

## Unknowns (to be resolved in Stage 1 recon)

- SPL's identity provider / middleware (BiblioCommons? EZproxy? OpenAthens? OCLC? custom?).
- Exact redirect chain from SPL resource page → library login → WaPo subscription confirmation.
- Form selectors for SPL card + PIN, and for the WaPo sign-in challenge (if presented).
- Whether CAPTCHA appears on either side. If yes on every attempt, full automation is infeasible and the project pivots to "session keepalive + alert when manual login needed".
- The exact DOM signature that means "entitlement currently active" (used by the idempotency probe).

## Architecture

```
systemd timer (OnUnitActiveSec=4d, Persistent=true)
   │
   ▼
wapo-renew.service  →  /home/nach/wapo-auto-login/run.sh
   │
   ├─ op run --env-file=secrets.env  ◄── resolves op:// refs at runtime
   │     SPL_CARD, SPL_PIN, WAPO_EMAIL, WAPO_PASSWORD
   │
   ▼
docker run --rm \
   -v /home/nach/wapo-auto-login/profile:/profile \
   -v /home/nach/wapo-auto-login/debug:/debug \
   -e SPL_CARD -e SPL_PIN -e WAPO_EMAIL -e WAPO_PASSWORD \
   wapo-renew:latest
   │
   ▼
Container (Debian + Xvfb + headful Chromium + Playwright Python)
   │
   ├─ Launch persistent context from /profile  ◄── cookies survive runs
   │
   ├─ STEP 1: PROBE — visit washingtonpost.com/my-post/account/subscription
   │           ├─ Entitlement still active? → log "skip", exit 0
   │           └─ Lapsed? → STEP 2
   │
   ├─ STEP 2: RE-AUTH (selectors from Stage 1 recon)
   │           ├─ Open SPL WaPo resource page → "Access"
   │           ├─ Submit SPL card + PIN
   │           ├─ Follow redirect chain to washingtonpost.com
   │           ├─ Sign in to WaPo if challenged
   │           └─ Assert "subscription active" confirmation selector
   │
   ├─ On failure: dump screenshot + page HTML + Playwright trace to /debug/
   │              (rotate, keep last 5 runs)
   │
   └─ Append one-line result to /home/nach/wapo-auto-login/renew.log
        (journald also has it for free via systemd)
```

### Key design decisions

- **Probe-first idempotency.** Most runs are a sub-second "still active" check; full login only runs when needed. Minimizes bot-detection exposure.
- **Persistent browser profile** on host-mounted volume. Cookies, localStorage, and Chromium device fingerprint survive across runs — looks like a returning user, not a fresh bot.
- **Headful Chromium under Xvfb** (not pure headless). More believable to bot mitigation; Xvfb provides the virtual display on the headless box.
- **systemd timer with `Persistent=true`**, not cron. Catches up after seattle-server reboots; journald gives free log retention.
- **Cadence: every 4 days.** Within the 3–5 day recommended window. Two-day buffer against a single failed run before the entitlement lapses.
- **Two credential pairs** (SPL card+PIN, WaPo email+password) resolved via `op run` from 1Password at runtime. Secrets never written to disk on seattle-server (1P service account token is the only persistent secret on disk).
- **Ephemeral container** (`--rm`). Nothing to restart on reboot; the timer is the only persistent piece.
- **All-Docker convention.** Matches the existing seattle-server pattern (HA, ESPHome, Caddy, Pi-hole all in Docker).
- **Failure observability.** Log-to-file only (per user preference). No active notifications. Failures discovered when the WaPo paywall comes back; debug artifacts available in `/debug/` for postmortem.

## File layout

**On seattle-server:**
```
/home/nach/wapo-auto-login/
├── docker/
│   ├── Dockerfile              # mcr.microsoft.com/playwright/python base + Xvfb
│   └── renew.py                # Probe → re-auth → log
├── secrets.env                 # op:// references only (no actual secrets)
├── run.sh                      # Wrapper: op run + docker run, appends to log
├── profile/                    # Persistent Chromium profile (volume)
├── debug/                      # Last 5 runs of failure artifacts
└── renew.log                   # Append-only one-line-per-run log

/etc/systemd/system/
├── wapo-renew.service          # Type=oneshot, ExecStart=/home/nach/wapo-auto-login/run.sh
└── wapo-renew.timer            # OnUnitActiveSec=4d, Persistent=true

/home/nach/.config/op/
└── service-account-token       # mode 600, owner nach
```

**Repo layout on this Mac (development):**
```
~/Projects/wapo-auto-login/
├── docs/superpowers/specs/2026-05-30-wapo-auto-login-design.md
├── docker/
│   ├── Dockerfile
│   └── renew.py
├── recon/                      # Stage 1 artifacts (gitignored except notes)
│   ├── trace.zip               # Playwright trace from codegen session
│   ├── flow-notes.md           # IdP, redirect chain, selectors captured
│   └── recorded.py             # Raw codegen output
├── secrets.env.example         # Template, no real creds
├── run.sh
├── README.md
└── .gitignore                  # excludes profile/, debug/, secrets.env, recon/{trace,recorded}
```

## 1Password items

Assumed in `Private` vault (confirm during implementation; rename in spec if different):

- `WaPo SPL` — fields: `username` (email), `password`
- `Seattle Public Library` — fields: `card_number`, `pin`

`secrets.env` contains only `op://` references:
```
WAPO_EMAIL=op://Private/WaPo SPL/username
WAPO_PASSWORD=op://Private/WaPo SPL/password
SPL_CARD=op://Private/Seattle Public Library/card_number
SPL_PIN=op://Private/Seattle Public Library/pin
```

A 1Password **service account** token is provisioned for unattended use, stored at `/home/nach/.config/op/service-account-token` (mode 600). `run.sh` exports it as `OP_SERVICE_ACCOUNT_TOKEN` before invoking `op run`.

## Stage 1 — Reconnaissance (prerequisite to implementation)

Before any container code is written, the actual login flow must be captured.

1. From this Mac (`~/Projects/wapo-auto-login`):
   - `playwright codegen --target=python --output=recon/recorded.py --save-trace=recon/trace.zip https://www.spl.org/books-and-media/digital-magazines-and-newspapers/the-washington-post-digital`
   - A fresh Chromium window opens (separate from regular Chrome — existing sessions untouched).
2. User drives the browser:
   - Click "Access" on the SPL page
   - Sign in with SPL card + PIN
   - Follow the redirect chain to washingtonpost.com
   - Sign in to WaPo if prompted
   - Land on the "subscription activated" confirmation page
3. Close the browser. Codegen drops `recon/recorded.py` (every action and selector) and `recon/trace.zip` (full network + DOM trace, replayable with `playwright show-trace recon/trace.zip`).
4. Extract into `recon/flow-notes.md`:
   - SPL IdP type (BiblioCommons / EZproxy / OpenAthens / OCLC / custom)
   - Full redirect chain (URLs in order)
   - Form selectors for each credential entry step
   - Success-state DOM signature (used by the idempotency probe)
   - Whether CAPTCHA appeared, and on which surface

**Decision gate:** if CAPTCHA appears on every attempt, halt implementation and pivot to "session keepalive + alert on lapse". `flow-notes.md` documents the call.

## Container

Base image: `mcr.microsoft.com/playwright/python:v1.49.0-jammy`.

Add:
- `xvfb`, `xauth`
- Project script `renew.py`
- Entrypoint that starts `Xvfb :99` in background, exports `DISPLAY=:99`, then runs `renew.py`

`renew.py` structure:
```python
# Pseudocode — exact selectors filled in after Stage 1
def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir="/profile",
            headless=False,                 # headful + Xvfb
            viewport={"width": 1280, "height": 800},
        )
        page = ctx.new_page()
        if probe_entitlement_active(page):
            log("skip: entitlement still active")
            return 0
        reauth_via_spl(page)
        if not probe_entitlement_active(page):
            dump_debug(page, "post-reauth probe still inactive")
            return 1
        log("ok: re-authenticated")
        return 0
```

The probe visits `https://www.washingtonpost.com/my-post/account/subscription` and asserts on a DOM signature captured in Stage 1 (e.g., presence of an "Active" badge or absence of a "Subscribe" CTA — Stage 1 picks one).

## Scheduling

systemd timer + oneshot service.

`wapo-renew.timer`:
```ini
[Unit]
Description=Refresh Washington Post SPL entitlement

[Timer]
OnCalendar=Mon,Fri 04:00
Persistent=true
RandomizedDelaySec=2h

[Install]
WantedBy=timers.target
```

`OnCalendar=Mon,Fri 04:00` gives an alternating 3-day / 4-day cadence — within the recommended 3–5 day window. `Persistent=true` only takes effect with calendar timers (not `OnUnitActiveSec=`); it stores last-run timestamp and catches up if seattle-server was off when a run was due.

`wapo-renew.service`:
```ini
[Unit]
Description=Refresh Washington Post SPL entitlement
After=docker.service tailscaled.service
Requires=docker.service

[Service]
Type=oneshot
User=nach
WorkingDirectory=/home/nach/wapo-auto-login
ExecStart=/home/nach/wapo-auto-login/run.sh
```

`RandomizedDelaySec=2h` smears the run across a 2-hour window so it's not a perfect every-96-hours-on-the-dot signal.

## Logging

`renew.log` line format (TSV, easy to grep):
```
2026-05-30T04:17:33Z  ok      skip-still-active   probe=200 selector=active-badge
2026-06-03T05:42:11Z  ok      reauth-success      duration=23s
2026-06-07T04:09:50Z  fail    spl-login-timeout   debug=/debug/2026-06-07T04-09-50/
```

On failure, `/debug/<timestamp>/` contains:
- `screenshot.png` — final page state
- `page.html` — final DOM
- `trace.zip` — Playwright trace (replayable with `playwright show-trace`)

Debug dir is auto-rotated to keep the most recent 5 failed runs.

## Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| CAPTCHA on WaPo or SPL | Re-auth times out waiting for confirmation selector; debug artifacts show CAPTCHA challenge | Manual login on Mac (or seattle-server via VNC into Xvfb if needed). Profile updates; next scheduled run resumes. |
| SPL or WaPo changes form selectors | Same as above | Re-run Stage 1 recon; update `renew.py`. |
| 1Password service account token expires/revoked | `op run` fails; `run.sh` exits non-zero; nothing runs | Rotate token in 1P, replace file. |
| seattle-server offline at scheduled time | Timer misses run | `Persistent=true` runs at next boot. |
| Profile volume corrupted | Persistent context fails to launch | Delete `/profile/`, next run does a full login from cold. |
| WaPo password rotated outside automation | Re-auth fails at WaPo sign-in step | Update 1P item; next run picks it up via `op run`. |

## Security considerations

- SPL card + PIN and WaPo password live only in 1Password. On disk on seattle-server: only the 1P service account token (mode 600, owner nach).
- `secrets.env` contains `op://` references, not values — safe to check in (committed as `secrets.env.example`; the real file with identical content lives on the server but is gitignored as a safety measure in case real values are ever pasted in by mistake).
- Container runs as non-root (Playwright base image's `pwuser`).
- Profile volume contains session cookies — equivalent to a logged-in browser. Stored under `/home/nach/wapo-auto-login/profile/` with default user perms; treat as sensitive but not catastrophic.
- ToS note: automating personal single-user logins to refresh a free entitlement is lower-risk than scraping content, but may still violate WaPo or SPL terms. This is for personal use; accept the risk.

## Out of scope (deliberately)

- No active notifications. Log-to-file only per user preference. Failure discovered when paywall returns.
- No web UI, no dashboard, no metrics export.
- No multi-user support, no credential rotation beyond manual 1P edits.
- No fallback to a different newspaper/library if SPL/WaPo partnership ends.

## Implementation order

1. **Stage 1 recon** (Mac, manual) → produces `recon/flow-notes.md`
2. **Decision gate**: CAPTCHA review. Proceed or pivot.
3. Scaffold repo: `Dockerfile`, `renew.py` skeleton, `run.sh`, `secrets.env.example`, `.gitignore`, `README.md`
4. Implement `renew.py` against the Stage 1 selectors; test locally on Mac with `docker run` (no systemd yet)
5. Provision 1P service account token; verify `op run` resolution
6. Deploy to seattle-server: copy repo, build image, place service account token
7. Install + enable systemd timer + service
8. Manual `systemctl start wapo-renew.service`; confirm success in `renew.log` and journald
9. Wait 4 days; verify scheduled run fires and succeeds

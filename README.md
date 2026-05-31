# wapo-auto-login

Unattended re-authentication to The Washington Post via the Seattle Public Library partnership, running on a home server.

If you're a Seattle Public Library cardholder, [SPL gives you free Washington Post Digital access](https://www.spl.org/books-and-media/digital-magazines-and-newspapers/the-washington-post-digital) — but the entitlement lapses every ~7 days and you have to manually re-walk the login flow each time. This automates that walk.

> **⚠️ Geo-restricted.** WaPo checks the request IP against the SPL partnership's allowed region. The host running this script needs a public IP that geolocates to **Washington State** (almost certainly the Seattle metro; foreign and out-of-state IPs are known to fail silently — the activation API returns 200-but-doesn't-mint, or the offer page swaps to an ineligible variant). If your home server is in WA, you're fine. If you tunnel out via a VPN exit node outside WA, this will stop working until you route back through WA.

```
2026-05-31T07:22:30Z	ok	reauth-success	            duration=6s
2026-05-31T07:23:19Z	ok	skip-still-active	    duration=3s
2026-06-03T11:48:02Z	ok	reauth-success	            duration=7s
```

## How it works

SPL's "use this link" on their WaPo resource page is just a static link to a Washington Post special-offers URL with a query parameter (`?s_oe=SPECIALOFFER_SEATTLEPL`). WaPo recognizes the parameter and mints a free-trial-class entitlement on whichever WaPo account signs in via that URL. The entitlement lapses; each subsequent visit re-mints it. There is no SPL identity provider in the loop — once you have a WaPo account that's been bootstrapped via the SPL link, all the script needs is your WaPo credentials.

So this project:

1. Visits the special-offers URL with a persistent Chromium profile (so cookies survive across runs).
2. If WaPo shows the sign-in form (cookies lapsed), fills email + password and submits — the activation API fires and re-mints the entitlement.
3. If WaPo shows "Looks like you're already a subscriber" (entitlement still active), exits with `skip-still-active`.
4. On any failure, dumps a screenshot, the page HTML, and a Playwright trace under `debug/` for postmortem.

```
systemd timer (Mon,Fri 04:00 + 0–2h jitter)
        │
        ▼
run.sh                                 ← reads 1P service-account token
   │                                       runs `op run --env-file=secrets.env`
   ▼                                       to resolve WaPo creds at runtime
docker run --rm                        ← ephemeral container per invocation
   -v ./profile:/profile                  (Chromium profile, host-mounted)
   -v ./debug:/debug                      (failure dumps, last 5 kept)
   -e WAPO_EMAIL -e WAPO_PASSWORD
   wapo-renew:latest
        │
        ▼
Xvfb :99  +  Playwright (Chromium)     ← headful under virtual display
        │                                  (less bot-detectable than headless)
        ▼
Visit special-offers URL → race two states:
        ┌───────────────────────────┐  ┌────────────────────────────┐
        │ "Email address" textbox   │  │ "Looks like you're already │
        │  → sign in, wait for      │  │  a subscriber"             │
        │    activation API → 200   │  │  → log skip-still-active   │
        └───────────────────────────┘  └────────────────────────────┘
                  │                                │
                  ▼                                ▼
        log: ok reauth-success       log: ok skip-still-active
        + tee renew.log + journald
```

## Repository layout

```
.
├── docker/
│   ├── Dockerfile              # Playwright Python base + Xvfb + non-root pwuser
│   ├── entrypoint.sh           # start Xvfb, exec renew.py
│   ├── renew.py                # the script: visit URL, sign in if needed, log
│   └── utils.py                # format_log_line, rotate_debug (TDD'd)
├── tests/test_utils.py         # pytest for utils
├── systemd/
│   ├── wapo-renew.service      # oneshot, runs as user nach
│   └── wapo-renew.timer        # Mon,Fri 04:00, Persistent=true, 2h jitter
├── run.sh                      # host wrapper: op run + docker run + tee log
├── secrets.env.example         # op:// references template (no values)
├── recon/flow-notes.md         # Stage 1 reconnaissance: selectors + API
└── docs/superpowers/
    ├── specs/2026-05-30-wapo-auto-login-design.md   # design rationale
    └── plans/2026-05-30-wapo-auto-login.md           # implementation plan
```

## Requirements

- **A host with a Washington State IP.** The SPL ↔ WaPo partnership geo-restricts the entitlement to in-state requests (see callout above). This is the most common reason the script "runs successfully" but the paywall comes back anyway.
- A Linux host (tested on Ubuntu 24.04, x86_64)
- Docker (the user running this in the docker group)
- systemd
- [1Password CLI](https://developer.1password.com/docs/cli/get-started) v2.30+
- A 1Password account, with:
  - A login item containing your WaPo account email + password
  - A service account that has **read access** to the vault holding that item
  - A service-account token saved at `~/.config/op/service-account-token` (mode 600)
- A WaPo account that's been bootstrapped at least once via [SPL's link](https://www.spl.org/books-and-media/digital-magazines-and-newspapers/the-washington-post-digital) (or your library's equivalent)
- An SPL library card (or your library's equivalent that participates in the same WaPo partnership). The card isn't used by the script — it's needed to legitimately bootstrap the WaPo account in the first place.

## Deploy

```bash
# On the target host:
git clone https://github.com/<you>/wapo-auto-login.git ~/wapo-auto-login
cd ~/wapo-auto-login

# Configure: point op:// refs at your 1P item paths.
cp secrets.env.example secrets.env
$EDITOR secrets.env

# Build the image.
cd docker && docker build -t wapo-renew:latest . && cd ..

# Drop your 1P service-account token here, mode 600.
mkdir -p ~/.config/op
chmod 700 ~/.config/op
# (paste token via your preferred secret-handling flow)
chmod 600 ~/.config/op/service-account-token

# Smoke test. Should log either reauth-success (cold) or skip-still-active (warm).
./run.sh
tail -1 renew.log

# Install + enable the timer.
sudo install -m 644 systemd/wapo-renew.service /etc/systemd/system/
sudo install -m 644 systemd/wapo-renew.timer  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wapo-renew.timer

# Verify schedule.
systemctl list-timers wapo-renew.timer
```

The unit files assume the project lives at `/home/nach/wapo-auto-login` and runs as user `nach`. Adjust `User=` and `WorkingDirectory=` in `systemd/wapo-renew.service` if your paths differ.

## Operating

- Logs: `renew.log` in the project root, and `journalctl -u wapo-renew.service`.
- One log line per run, tab-separated: `<ISO8601-UTC>\t<status>\t<kind>\t<detail>`.
- Failures dump screenshot + HTML + Playwright trace under `debug/<ISO8601>/`. The last 5 are kept.
- Replay a failure trace: `playwright show-trace debug/<timestamp>/trace.zip`.
- The Chromium profile persists across runs at `profile/`. Wipe it (`rm -rf profile`) to force a fresh sign-in on the next run.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `fail exception err=TimeoutError` | WaPo changed selectors, or activation API URL changed | Re-run Stage 1 recon (`playwright codegen`), update constants at top of `docker/renew.py`, rebuild |
| `fail missing-op-token path=…` | Service-account token missing or unreadable | Restore the token file at the expected path, mode 600 |
| `fail exception err=PWError` and the screenshot shows a CAPTCHA | WaPo started challenging this account | The bot can't solve CAPTCHAs. Wipe `profile/`, sign in once manually (e.g. via VNC into Xvfb on the host), let cookies populate the profile, then re-enable the timer |
| Runs log `reauth-success` but the paywall is still there in your browser | Host IP is outside Washington State | Geo-restriction (see the callout at the top). Check the host's public IP geolocation; move the host or route through a WA-state exit |
| `Permission denied (13)` on `/profile/SingletonLock` (Linux) | Mount source dirs got root-owned because Docker created them on first run | Already handled by `run.sh` (it `mkdir -p`s the dirs as the host user). If you hit this manually, `chown -R $USER:$USER profile/ debug/` |
| Service runs but the container can't connect to Docker | The systemd-running user isn't in the `docker` group | `sudo usermod -aG docker $USER`, then log out / log in (group membership applies to new sessions) |

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pytest playwright
playwright install chromium
pytest                                       # unit tests
cd docker && docker build -t wapo-renew:latest . && cd ..
./run.sh                                     # end-to-end against live WaPo
```

The Playwright codegen flow that produced `recon/flow-notes.md`:

```bash
mkdir -p recon
playwright codegen \
  --target=python \
  --output=recon/recorded.py \
  --save-har=recon/network.har \
  https://www.spl.org/books-and-media/digital-magazines-and-newspapers/the-washington-post-digital
```

Walk through the SPL → WaPo flow manually in the spawned Chromium; selectors, redirects, and the activation API URL fall out of the recorded script and HAR. `recon/recorded.py` and `recon/network.har` are gitignored because the codegen records your real password in them — treat as sensitive and rotate the password if they accidentally escape.

## Caveats

- **Geo-restricted to Washington State** (re-emphasized — this catches everyone). The script will run, log `reauth-success`, and look healthy from an out-of-state host, but the WaPo paywall in your browser will not actually lift. Verify by visiting [a paywalled WaPo article](https://www.washingtonpost.com/) in a regular browser after the first run.
- **Personal single-user use only.** This automates your own credentials against your own WaPo account. Don't share, don't multi-tenant.
- **Library and newspaper ToS** generally restrict automated access. Refreshing your own personal entitlement is a low-risk grey area; scraping or redistributing content is not. Proceed at your own risk.
- **Brittle by nature.** This will break the day WaPo changes their sign-in selectors or the activation API URL. The fix is straightforward (re-run Stage 1 recon, update three constants), but there's no graceful degradation — you'll just see `fail` in `renew.log` and stop getting renewals.
- **Not a paywall bypass.** This relies on the specific SPL ↔ WaPo partnership, which the library already offers to cardholders. It's not a general newspaper-access trick.
- **Other libraries**: many US public libraries have the same WaPo partnership ([NYPL](https://www.nypl.org/), [LAPL](https://www.lapl.org/), [BPL](https://www.bklynlibrary.org/), etc.). Each has its own `s_oe=…` parameter **and its own geo-restriction** (typically the library's home state). You'd need to capture yours via Stage 1 recon, swap the constant in `docker/renew.py`, and run from a host inside the allowed region.

## License

MIT. See LICENSE.

# wapo-auto-login

Automated weekly re-authentication to The Washington Post via Seattle Public Library, running unattended on `seattle-server`.

## What it does

Every Monday and Friday at 04:00 (local time, +/- 2h jitter), `seattle-server` runs a headless Chromium that:

1. Loads `https://www.washingtonpost.com/subscribe/signin/special-offers/?s_oe=SPECIALOFFER_SEATTLEPL` using a persistent Chromium profile (cookies survive across runs).
2. If the WaPo sign-in form is visible, fills in email + password (two-step sign-in).
3. Waits for the activation API (`POST .../subscriptionapi/v2/subscriptions/special-offers`) to return 200 — that's the signal the entitlement was minted.

## Architecture

See `docs/superpowers/specs/2026-05-30-wapo-auto-login-design.md`.

## Files

- `docker/` — container that runs the script (Playwright Python + Xvfb)
- `run.sh` — host wrapper: resolves secrets via `op run`, calls `docker run`, appends to `renew.log`
- `systemd/` — `wapo-renew.service` + `wapo-renew.timer`
- `secrets.env.example` — 1Password reference template
- `recon/flow-notes.md` — captured Stage 1 reconnaissance (IdP, selectors, redirect chain)

## Deploy from scratch

1. Clone to `/home/nach/wapo-auto-login` on seattle-server.
2. `cp secrets.env.example secrets.env`, edit if 1P item names differ.
3. Install `op` CLI (v2.30+); create a 1P service account with read access to the vault holding the WaPo item.
4. Save the service account token to `~/.config/op/service-account-token`, mode 600.
5. `cd docker && docker build -t wapo-renew:latest .`
6. Smoke test: `./run.sh` — should log `reauth-success` or `refresh-already-signed-in`.
7. Install systemd units:
   ```
   sudo install -m 644 systemd/wapo-renew.service /etc/systemd/system/
   sudo install -m 644 systemd/wapo-renew.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now wapo-renew.timer
   ```

## Troubleshooting

- **`renew.log` shows `fail`** → check `debug/<latest>/`. Replay the trace with `playwright show-trace debug/<latest>/trace.zip`.
- **`missing-op-token`** → service account token missing or unreadable at `~/.config/op/service-account-token`.
- **CAPTCHA in the screenshot** → the bot can't solve it. Log in manually once on seattle-server (e.g., wipe `profile/` and re-run from a desktop with screen sharing). Profile updates; next scheduled run resumes.
- **Selectors changed** → re-run Stage 1 recon on the Mac (`playwright codegen`), update constants at the top of `docker/renew.py`, rebuild + redeploy.

## Local development

```
python3 -m venv .venv && source .venv/bin/activate
pip install pytest playwright
playwright install chromium
pytest                              # unit tests for utils.py
cd docker && docker build -t wapo-renew:latest . && cd ..
./run.sh                            # end-to-end against live WaPo
```

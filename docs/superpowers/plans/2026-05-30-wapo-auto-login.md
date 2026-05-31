# WaPo Auto-Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an unattended weekly job on `seattle-server` that drives a headless browser to the WaPo SPL special-offers URL and re-signs in if needed, refreshing nach's WaPo entitlement before it lapses.

**Architecture:** Playwright (Python) running headful Chromium under Xvfb inside a Docker container. Persistent browser profile on a host-mounted volume; probe-first idempotency so most runs are a sub-second "still active" check. Scheduled by a systemd timer (`Mon,Fri 04:00` with `Persistent=true`). Secrets resolved at runtime via `op run` from a 1Password service account; nothing sensitive on disk except the service-account token (mode 600).

**Tech Stack:** Python 3, Playwright, Xvfb, Docker, systemd, 1Password CLI (`op`), bash.

**Spec:** `docs/superpowers/specs/2026-05-30-wapo-auto-login-design.md`

**Testing philosophy:** Pure helpers (log formatting, debug rotation) are unit-tested with pytest. Browser-driving functions are validated by end-to-end smoke runs against the live SPL + WaPo sites — there is no useful mock for "did the bot actually log in." Failures produce a screenshot + DOM + Playwright trace under `debug/` for postmortem.

---

## File Structure

**To create:**
- `docker/Dockerfile` — Playwright Python base + Xvfb + entrypoint
- `docker/entrypoint.sh` — start Xvfb, exec `renew.py`
- `docker/renew.py` — the script: probe → re-auth → log
- `docker/utils.py` — pure helpers (log formatter, debug rotation, env validation)
- `tests/test_utils.py` — pytest unit tests for `utils.py`
- `run.sh` — host wrapper: `op run` + `docker run` + append-to-log
- `secrets.env.example` — `op://` reference template
- `systemd/wapo-renew.service` — oneshot unit
- `systemd/wapo-renew.timer` — `Mon,Fri 04:00` calendar timer
- `recon/flow-notes.md` — Stage 1 captured IdP, redirect chain, selectors, success signature
- `README.md` — what this is, how to deploy, how to debug

**Already exists:** `.gitignore`, `docs/superpowers/specs/2026-05-30-wapo-auto-login-design.md`

---

## Task 0: GitHub repo + feature branch

User preference (`~/.claude/CLAUDE.md`) is to end work with a PR. Set up the remote up-front; all implementation tasks commit to a feature branch and we open the PR at the end.

**Files:** none (git only).

- [ ] **Step 1: Create GitHub repo (private)**

```bash
cd /Users/nach/Projects/wapo-auto-login
gh repo create wapo-auto-login --private --source=. --remote=origin --description "Automate weekly WaPo re-auth via Seattle Public Library"
git push -u origin main
```

Expected: `https://github.com/<user>/wapo-auto-login` URL printed; `main` pushed (1 commit, the spec).

- [ ] **Step 2: Create feature branch for all implementation work**

```bash
git checkout -b feat/initial-implementation
```

- [ ] **Step 3: Commit a marker (empty commit is fine — keeps the branch alive even if first real task is delayed)**

Skip — first real commit comes at the end of Task 1.

---

## Task 1: Stage 1 reconnaissance — ✅ COMPLETE (2026-05-30)

Findings captured in `recon/flow-notes.md`. Notable surprise: the SPL "library access" link is just a static link to `https://www.washingtonpost.com/subscribe/signin/special-offers/?s_oe=SPECIALOFFER_SEATTLEPL` — there is no SPL library-card login form anywhere in the flow. The whole project simplified: one credential pair (WaPo email + password), one URL, no separate probe. Decision: PROCEED (no CAPTCHA observed). Task 6 below reflects the simplified flow with real selectors filled in.

The instructions below remain as a record of the recon process for posterity.

Capture the actual SPL → WaPo login flow before writing any production code. This is the prerequisite to every later task.

**Files:**
- Create: `recon/flow-notes.md`
- Create (gitignored): `recon/recorded.py`, `recon/trace.zip`

- [ ] **Step 1: Install Playwright on the Mac if not already**

```bash
cd /Users/nach/Projects/wapo-auto-login
python3 -m venv .venv
source .venv/bin/activate
pip install playwright
playwright install chromium
```

Expected: Chromium download (~140MB) completes.

- [ ] **Step 2: Run codegen against the SPL WaPo resource page**

```bash
mkdir -p recon
playwright codegen \
  --target=python \
  --output=recon/recorded.py \
  --save-trace=recon/trace.zip \
  https://www.spl.org/books-and-media/digital-magazines-and-newspapers/the-washington-post-digital
```

Expected: a Chromium window opens, plus the Playwright Inspector window.

- [ ] **Step 3: Drive the flow manually (user action)**

In the spawned Chromium:
1. Click the "Access" link/button on the SPL page
2. Sign in with SPL library card + PIN
3. Follow the redirect chain to washingtonpost.com
4. Sign in to WaPo if prompted (use the existing WaPo account credentials)
5. Land on the "subscription activated" confirmation page (or the subscription account page showing "active" status)
6. Close the browser

Expected: `recon/recorded.py` written (auto-generated script), `recon/trace.zip` written (~5-20 MB).

- [ ] **Step 4: Replay the trace to inspect the flow**

```bash
playwright show-trace recon/trace.zip
```

Expected: a trace viewer opens with network + DOM snapshots for every action.

- [ ] **Step 5: Write `recon/flow-notes.md`**

Extract from `recorded.py` + the trace viewer:

```markdown
# SPL → WaPo Login Flow

## Identity provider
- Type: [BiblioCommons / EZproxy / OpenAthens / OCLC / custom]
- Login URL: <exact URL>

## Redirect chain (in order)
1. https://www.spl.org/.../washington-post-digital
2. <next URL>
3. ...
N. https://www.washingtonpost.com/<confirmation page>

## Form selectors
### SPL card login
- Card-number input: `<CSS or text selector from recorded.py>`
- PIN input: `<selector>`
- Submit button: `<selector>`

### WaPo sign-in (if prompted)
- Email input: `<selector>`
- Continue button: `<selector>`
- Password input: `<selector>`
- Sign-in button: `<selector>`

## Probe — "entitlement is active" signature
- URL to visit: `https://www.washingtonpost.com/my-post/account/subscription` (or whichever page from the trace shows entitlement state)
- Selector that ONLY exists when entitlement is active: `<selector>`
- Selector that ONLY exists when entitlement is lapsed: `<selector>` (e.g., a "Subscribe" CTA)

## CAPTCHA observations
- Did CAPTCHA appear on SPL login? [yes/no]
- Did CAPTCHA appear on WaPo sign-in? [yes/no]
- If yes anywhere: which provider (reCAPTCHA, hCaptcha, Cloudflare Turnstile)?

## Decision
- [ ] PROCEED — no CAPTCHA, automation viable
- [ ] PIVOT — CAPTCHA blocks unattended runs; revise plan to "session keepalive + manual re-login alert"
```

- [ ] **Step 6: Commit notes**

```bash
git add recon/flow-notes.md
git commit -m "Stage 1 recon: capture SPL→WaPo login flow"
```

Note: `recon/recorded.py` and `recon/trace.zip` are excluded by `.gitignore` (contains identifying URLs and DOM snippets that may include card-number echoes).

- [ ] **Step 7: DECISION GATE**

If `flow-notes.md` records CAPTCHA on every attempt: **stop the plan**. Open a discussion about pivoting to "session keepalive + alert on lapse" — that's a different design.

Otherwise: proceed to Task 2.

---

## Task 2: Repo scaffolding

Create the empty file skeleton so later tasks have a place to write code.

**Files:**
- Create: `docker/Dockerfile` (placeholder)
- Create: `docker/entrypoint.sh` (placeholder)
- Create: `docker/renew.py` (placeholder)
- Create: `docker/utils.py` (placeholder)
- Create: `tests/test_utils.py` (placeholder)
- Create: `secrets.env.example`
- Modify: `.gitignore` (add `.venv/`, `__pycache__/`, `.pytest_cache/`)

- [ ] **Step 1: Create empty source files**

```bash
mkdir -p docker tests systemd
touch docker/Dockerfile docker/entrypoint.sh docker/renew.py docker/utils.py
touch tests/test_utils.py
chmod +x docker/entrypoint.sh
```

- [ ] **Step 2: Write `secrets.env.example`**

```bash
cat > secrets.env.example <<'EOF'
# Real values are resolved at runtime by `op run --env-file=secrets.env -- ...`
# Copy this file to secrets.env on each host and fill in the op:// references
# matching your actual 1Password item names.
WAPO_EMAIL=op://Private/WaPo SPL/username
WAPO_PASSWORD=op://Private/WaPo SPL/password
EOF
```

- [ ] **Step 3: Extend `.gitignore`**

Read current `.gitignore`, then append:

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 4: Commit the skeleton**

```bash
git add docker/ tests/ systemd/ secrets.env.example .gitignore
git commit -m "Scaffold project skeleton and secrets template"
```

---

## Task 3: Dockerfile + entrypoint

Build the container image once, end-to-end, before writing the Python script. Catches base-image surprises early.

**Files:**
- Modify: `docker/Dockerfile`
- Modify: `docker/entrypoint.sh`

- [ ] **Step 1: Write `docker/Dockerfile`**

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Xvfb gives us a virtual display so Chromium can run "headful" on a headless host.
# Headful + persistent profile is significantly less detectable than pure headless.
RUN apt-get update \
 && apt-get install -y --no-install-recommends xvfb xauth \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY entrypoint.sh /app/entrypoint.sh
COPY renew.py /app/renew.py
COPY utils.py /app/utils.py

# The base image creates a non-root `pwuser`; run as that user.
RUN chown -R pwuser:pwuser /app
USER pwuser

ENTRYPOINT ["/app/entrypoint.sh"]
```

- [ ] **Step 2: Write `docker/entrypoint.sh`**

```bash
#!/bin/bash
set -euo pipefail

# Start Xvfb on display :99 in the background. Chromium will connect to it.
Xvfb :99 -screen 0 1280x800x24 -ac +extension RANDR &
XVFB_PID=$!
export DISPLAY=:99

# Give Xvfb a beat to come up.
sleep 1

# Run the script. Any non-zero exit propagates out of the container.
python /app/renew.py
EXIT=$?

kill "$XVFB_PID" 2>/dev/null || true
exit "$EXIT"
```

- [ ] **Step 3: Write a stub `docker/renew.py` so the image will build and run**

```python
#!/usr/bin/env python3
"""Stub — replaced in Task 5/6/7."""
print("renew.py stub — full implementation coming in later tasks")
```

- [ ] **Step 4: Write a stub `docker/utils.py`**

```python
"""Stub — replaced in Task 4."""
```

- [ ] **Step 5: Build the image locally on the Mac**

```bash
cd docker
docker build -t wapo-renew:latest .
```

Expected: image build succeeds (first build pulls the ~600 MB Playwright base; subsequent builds use cache).

- [ ] **Step 6: Smoke-test the container**

```bash
docker run --rm wapo-renew:latest
```

Expected output:
```
renew.py stub — full implementation coming in later tasks
```

- [ ] **Step 7: Commit**

```bash
cd ..
git add docker/Dockerfile docker/entrypoint.sh docker/renew.py docker/utils.py
git commit -m "Add Dockerfile with Xvfb + Playwright + stub entrypoint"
```

---

## Task 4: `utils.py` — log formatter (TDD)

Format a single log line. Pure function, easy to unit-test.

**Files:**
- Modify: `docker/utils.py`
- Modify: `tests/test_utils.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_utils.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "docker"))

from utils import format_log_line


def test_format_log_line_ok():
    line = format_log_line(
        timestamp="2026-05-30T04:17:33Z",
        status="ok",
        kind="skip-still-active",
        detail="probe=200 selector=active-badge",
    )
    assert line == (
        "2026-05-30T04:17:33Z\tok\tskip-still-active\tprobe=200 selector=active-badge"
    )


def test_format_log_line_fail_with_debug():
    line = format_log_line(
        timestamp="2026-06-07T04:09:50Z",
        status="fail",
        kind="spl-login-timeout",
        detail="debug=/debug/2026-06-07T04-09-50/",
    )
    assert line == (
        "2026-06-07T04:09:50Z\tfail\tspl-login-timeout\tdebug=/debug/2026-06-07T04-09-50/"
    )


def test_format_log_line_rejects_tab_in_detail():
    # Tabs in detail would break TSV parsing — reject at the boundary.
    import pytest
    with pytest.raises(ValueError):
        format_log_line(
            timestamp="2026-05-30T04:17:33Z",
            status="ok",
            kind="reauth-success",
            detail="duration=23s\tunexpected",
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/nach/Projects/wapo-auto-login
source .venv/bin/activate
pip install pytest
pytest tests/test_utils.py -v
```

Expected: 3 failures (`ImportError: cannot import name 'format_log_line'` or similar).

- [ ] **Step 3: Implement `format_log_line` in `docker/utils.py`**

```python
def format_log_line(*, timestamp: str, status: str, kind: str, detail: str) -> str:
    """Return one tab-separated log line. Reject tabs inside `detail` to keep TSV parseable."""
    if "\t" in detail:
        raise ValueError("detail must not contain tabs")
    return f"{timestamp}\t{status}\t{kind}\t{detail}"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_utils.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add docker/utils.py tests/test_utils.py
git commit -m "Add format_log_line helper with TDD"
```

---

## Task 5: `utils.py` — debug-dir rotation (TDD)

Keep only the most recent N failure dumps under `/debug/`.

**Files:**
- Modify: `docker/utils.py`
- Modify: `tests/test_utils.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_utils.py`:

```python
def test_rotate_debug_keeps_n_most_recent(tmp_path):
    from utils import rotate_debug

    # Create 7 timestamped subdirs; rotate to keep 5.
    for ts in ["2026-01-01T00-00-00", "2026-01-02T00-00-00", "2026-01-03T00-00-00",
               "2026-01-04T00-00-00", "2026-01-05T00-00-00", "2026-01-06T00-00-00",
               "2026-01-07T00-00-00"]:
        (tmp_path / ts).mkdir()

    rotate_debug(tmp_path, keep=5)

    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == [
        "2026-01-03T00-00-00",
        "2026-01-04T00-00-00",
        "2026-01-05T00-00-00",
        "2026-01-06T00-00-00",
        "2026-01-07T00-00-00",
    ]


def test_rotate_debug_noop_when_under_limit(tmp_path):
    from utils import rotate_debug
    (tmp_path / "2026-01-01T00-00-00").mkdir()
    (tmp_path / "2026-01-02T00-00-00").mkdir()
    rotate_debug(tmp_path, keep=5)
    assert len(list(tmp_path.iterdir())) == 2


def test_rotate_debug_ignores_non_directories(tmp_path):
    from utils import rotate_debug
    (tmp_path / "2026-01-01T00-00-00").mkdir()
    (tmp_path / "stray.txt").write_text("ignore me")
    rotate_debug(tmp_path, keep=1)
    assert (tmp_path / "stray.txt").exists()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_utils.py -v
```

Expected: 3 new failures (existing 3 still pass).

- [ ] **Step 3: Implement `rotate_debug` in `docker/utils.py`**

Append:

```python
from pathlib import Path


def rotate_debug(debug_dir: Path, *, keep: int) -> None:
    """Delete oldest timestamped subdirs of `debug_dir`, keeping the `keep` most recent.

    Subdirs are sorted lexicographically by name — our timestamp format (ISO-8601 with
    `-` instead of `:`) sorts the same as chronologically, so lexicographic == newest-first.
    """
    import shutil

    subdirs = sorted(
        (p for p in debug_dir.iterdir() if p.is_dir()),
        key=lambda p: p.name,
    )
    to_delete = subdirs[:-keep] if keep > 0 else subdirs
    for p in to_delete:
        shutil.rmtree(p)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_utils.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add docker/utils.py tests/test_utils.py
git commit -m "Add rotate_debug helper with TDD"
```

---

## Task 6: `renew.py` — sign-in flow + main

The browser-driving code. Selectors are filled in from `recon/flow-notes.md`. Cannot be meaningfully unit-tested (needs a real Chromium + live WaPo) — validated by the end-to-end smoke test in Task 8.

**Files:**
- Modify: `docker/renew.py`

- [ ] **Step 1: Write the full `docker/renew.py`**

Replace the stub with the implementation below. All selectors are captured from Stage 1 recon (see `recon/flow-notes.md`).

```python
#!/usr/bin/env python3
"""Refresh nach's WaPo entitlement via the Seattle Public Library special-offers URL.

The SPL "library access" link is a static link to a WaPo special-offers URL; visiting
it while logged in re-mints the free-trial entitlement. This script visits that URL,
signs in to WaPo if the form is shown, and waits for the entitlement API to fire.
"""
import os
import sys
import datetime
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout

from utils import format_log_line, rotate_debug

PROFILE_DIR = Path("/profile")
DEBUG_DIR = Path("/debug")
DEBUG_KEEP = 5

# Captured in Stage 1 recon (recon/flow-notes.md).
SPECIAL_OFFERS_URL = (
    "https://www.washingtonpost.com/subscribe/signin/special-offers/"
    "?s_oe=SPECIALOFFER_SEATTLEPL"
)
# The XHR whose 200 response signals "entitlement minted".
ACTIVATION_API_URL = (
    "https://subscribe.washingtonpost.com/subscriptionapi/v2/subscriptions/special-offers"
)


def now_ts() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def debug_dir_name() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


def log(*, status: str, kind: str, detail: str) -> None:
    line = format_log_line(timestamp=now_ts(), status=status, kind=kind, detail=detail)
    print(line, flush=True)  # journald + run.sh tee both capture stdout


def require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        log(status="fail", kind="missing-env", detail=f"env={name}")
        sys.exit(2)
    return val


def sign_in_if_needed(page: Page, *, wapo_email: str, wapo_password: str) -> bool:
    """If the WaPo sign-in form is visible on the current page, fill and submit it.

    Returns True if a sign-in was performed, False if the form was not shown
    (meaning the persistent profile already has a valid WaPo session).
    """
    email_input = page.get_by_role("textbox", name="Email address")
    try:
        email_input.wait_for(state="visible", timeout=10_000)
    except PWTimeout:
        return False

    # Two-step sign-in: email screen → password screen. Same button selector for both.
    email_input.fill(wapo_email)
    page.locator('[data-test-id="sign-in-btn"]').click()

    password_input = page.get_by_role("textbox", name="Password")
    password_input.wait_for(state="visible", timeout=15_000)
    password_input.fill(wapo_password)
    page.locator('[data-test-id="sign-in-btn"]').click()
    return True


def dump_debug(page: Page, kind: str) -> Path:
    target = DEBUG_DIR / debug_dir_name()
    target.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(target / "screenshot.png"), full_page=True)
        (target / "page.html").write_text(page.content())
    except Exception as e:
        (target / "dump-error.txt").write_text(f"{kind}: {e}\n{traceback.format_exc()}")
    return target


def main() -> int:
    wapo_email = require_env("WAPO_EMAIL")
    wapo_password = require_env("WAPO_PASSWORD")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    rotate_debug(DEBUG_DIR, keep=DEBUG_KEEP)

    started = datetime.datetime.now(datetime.timezone.utc)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,  # Xvfb supplies the display
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = ctx.new_page()

        try:
            # Set up the activation-API waiter BEFORE navigation so we can't miss
            # the response if it fires immediately on page load (returning user case).
            with page.expect_response(
                lambda r: r.url.startswith(ACTIVATION_API_URL) and r.status == 200,
                timeout=60_000,
            ) as response_info:
                page.goto(SPECIAL_OFFERS_URL, wait_until="domcontentloaded", timeout=30_000)
                signed_in = sign_in_if_needed(
                    page, wapo_email=wapo_email, wapo_password=wapo_password,
                )

            response_info.value  # raises if the wait timed out

            kind = "reauth-success" if signed_in else "refresh-already-signed-in"
            duration = (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()
            log(status="ok", kind=kind, detail=f"duration={int(duration)}s")
            return 0

        except Exception as e:
            target = dump_debug(page, kind="exception")
            try:
                ctx.tracing.stop(path=str(target / "trace.zip"))
            except Exception:
                pass
            log(status="fail", kind="exception", detail=f"err={type(e).__name__} debug={target}")
            return 1
        finally:
            try:
                ctx.tracing.stop()  # no-op if already stopped
            except Exception:
                pass
            ctx.close()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Rebuild the image**

```bash
cd docker
docker build -t wapo-renew:latest .
cd ..
```

Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add docker/renew.py
git commit -m "Implement renew.py: visit special-offers URL, sign in, wait for activation API"
```

---

## Task 7: Host wrapper script

`run.sh` is what systemd (and you, manually) invoke. It resolves secrets via `op run` and forwards them into `docker run`.

**Files:**
- Modify: `run.sh`

- [ ] **Step 1: Write `run.sh`**

```bash
#!/bin/bash
set -euo pipefail

# Paths are relative to the project root; cd there first.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1Password service account token. On seattle-server it lives at
# /home/nach/.config/op/service-account-token; on the Mac, override OP_TOKEN_FILE.
OP_TOKEN_FILE="${OP_TOKEN_FILE:-$HOME/.config/op/service-account-token}"

if [[ ! -f "$OP_TOKEN_FILE" ]]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)	fail	missing-op-token	path=$OP_TOKEN_FILE" \
    | tee -a renew.log
  exit 2
fi

OP_SERVICE_ACCOUNT_TOKEN="$(cat "$OP_TOKEN_FILE")"
export OP_SERVICE_ACCOUNT_TOKEN

# `op run --env-file=secrets.env` resolves the op:// references and exports
# the real values into the child process environment (never written to disk).
# Those env vars are then forwarded into the container with `-e VAR`.
op run --env-file="$SCRIPT_DIR/secrets.env" -- \
  docker run --rm \
    -v "$SCRIPT_DIR/profile:/profile" \
    -v "$SCRIPT_DIR/debug:/debug" \
    -e WAPO_EMAIL \
    -e WAPO_PASSWORD \
    wapo-renew:latest \
  | tee -a renew.log
```

- [ ] **Step 2: Make executable**

```bash
chmod +x run.sh
```

- [ ] **Step 3: Commit**

```bash
git add run.sh
git commit -m "Add run.sh wrapper: op run + docker run, append to renew.log"
```

---

## Task 8: End-to-end smoke test on the Mac

Validates everything before touching seattle-server.

**Prerequisite — 1Password service account (one-time, manual):**
1. Log in to 1Password.com → Integrations → Service Accounts → "Create Service Account"
2. Name: `seattle-server-wapo-renew`
3. Vault access: read-only on the `Private` vault (or whichever vault holds the WaPo + SPL items)
4. Copy the token (shown once). Save to `~/.config/op/service-account-token` on the Mac, mode 600:

```bash
mkdir -p ~/.config/op
# Paste the token at the prompt; this avoids putting it in shell history.
read -s -p "Paste service account token: " token && echo "$token" > ~/.config/op/service-account-token && chmod 600 ~/.config/op/service-account-token && unset token
```

**Files:** none new.

- [ ] **Step 1: Confirm `op` CLI is installed and the token resolves**

```bash
brew install --cask 1password-cli 2>/dev/null || true
export OP_SERVICE_ACCOUNT_TOKEN="$(cat ~/.config/op/service-account-token)"
op whoami
```

Expected: prints service account info (`URL`, `Email: service account`).

- [ ] **Step 2: Verify the actual 1P item paths**

```bash
op item get "WaPo SPL" --format json | jq '.fields[] | {label,id}'
```

Expected: lists fields. **If item names or field labels differ from the spec assumptions, update `secrets.env.example` and re-stage it** (no commit yet — Task 9 will be a follow-up if needed).

- [ ] **Step 3: Create real `secrets.env` from the template**

```bash
cp secrets.env.example secrets.env
```

`.gitignore` already excludes `secrets.env`. The file contains only op:// references, never raw values.

- [ ] **Step 4: Sanity-check that `op run` can resolve everything**

```bash
op run --env-file=secrets.env -- bash -c 'echo "email: $WAPO_EMAIL  password length: ${#WAPO_PASSWORD}"'
```

Expected: prints something like `email: hermosillaignacio@gmail.com  password length: 24`. If `$WAPO_PASSWORD` length is 0, fix the op:// reference in `secrets.env`.

- [ ] **Step 5: First end-to-end run (empty profile → full login expected)**

```bash
./run.sh
```

Watch:
- Container starts, Xvfb spins up
- Script logs probe failure (expected — empty profile)
- Re-auth flow runs (~20-40s)
- Final log line: `ok	reauth-success	duration=Ns`
- `renew.log` has the line; `profile/` now contains Chromium profile artifacts

If it fails: inspect `debug/<latest>/` — screenshot, `page.html`, `trace.zip` (replay with `playwright show-trace debug/<latest>/trace.zip`).

- [ ] **Step 6: Verify entitlement is actually active**

In regular Chrome (or a private window), visit `https://www.washingtonpost.com/`. Log in with the WaPo account. Confirm: no paywall, no "Subscribe" CTA. If still paywalled, the bot's "success" assertion was wrong — re-do Stage 1 recon for the correct confirmation selector and update `renew.py`.

- [ ] **Step 7: Idempotency check — second run should skip**

```bash
./run.sh
```

Expected: log line `ok	skip-still-active	probe=...`, runtime < 5 seconds.

- [ ] **Step 8: If selectors needed fixing, commit those fixes**

```bash
git add docker/renew.py
git commit -m "Fix selectors after Mac smoke test"
```

---

## Task 9: Systemd units

**Files:**
- Modify: `systemd/wapo-renew.service`
- Modify: `systemd/wapo-renew.timer`

- [ ] **Step 1: Write `systemd/wapo-renew.service`**

```ini
[Unit]
Description=Refresh Washington Post SPL entitlement
After=docker.service tailscaled.service network-online.target
Requires=docker.service
Wants=network-online.target

[Service]
Type=oneshot
User=nach
Group=nach
WorkingDirectory=/home/nach/wapo-auto-login
ExecStart=/home/nach/wapo-auto-login/run.sh

# Limit per-invocation runtime; if the bot hangs, fail fast and let next cycle retry.
TimeoutStartSec=300

# Capture stdout/stderr to journald (in addition to renew.log).
StandardOutput=journal
StandardError=journal
```

- [ ] **Step 2: Write `systemd/wapo-renew.timer`**

```ini
[Unit]
Description=Refresh Washington Post SPL entitlement (timer)

[Timer]
# Mon and Fri 04:00 local time → alternating 3-day/4-day cadence (within the
# 3–5 day recommended window). RandomizedDelaySec smears across a 2h window so
# this isn't a perfect on-the-dot signal.
OnCalendar=Mon,Fri 04:00
RandomizedDelaySec=2h
# Persistent=true catches up if seattle-server was off when a run was due.
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Commit**

```bash
git add systemd/wapo-renew.service systemd/wapo-renew.timer
git commit -m "Add systemd service + timer (Mon,Fri 04:00 cadence)"
```

---

## Task 10: Deploy to seattle-server

Get the code + token onto the server and build the image there.

**Files:** none new on the Mac. Operations on `seattle-server`.

- [ ] **Step 1: Push the feature branch so it's reachable from the server**

```bash
git push -u origin feat/initial-implementation
```

- [ ] **Step 2: Clone on seattle-server**

```bash
ssh seattle "git clone https://github.com/<your-user>/wapo-auto-login.git /home/nach/wapo-auto-login && cd /home/nach/wapo-auto-login && git checkout feat/initial-implementation"
```

- [ ] **Step 3: Install `op` CLI on seattle-server**

```bash
ssh seattle <<'EOF'
set -euo pipefail
ARCH="amd64"  # adjust if the M700 is i386 — it's not, but defensive
curl -sSf https://cache.agilebits.com/dist/1P/op2/pkg/v2.30.3/op_linux_${ARCH}_v2.30.3.zip -o /tmp/op.zip
unzip -o /tmp/op.zip -d /tmp/op-extract
sudo mv /tmp/op-extract/op /usr/local/bin/op
sudo chmod +x /usr/local/bin/op
op --version
EOF
```

Expected: prints `2.30.3` or similar.

- [ ] **Step 4: Provision a fresh 1P service account token for the server**

Reuse the same service account from Task 8 OR create a separate one named `seattle-server-wapo-renew-prod` (slightly cleaner — independent rotation). Either way, paste the token into a file on seattle-server:

```bash
ssh seattle "mkdir -p ~/.config/op && touch ~/.config/op/service-account-token && chmod 600 ~/.config/op/service-account-token"
ssh seattle "cat > ~/.config/op/service-account-token" <<< "PASTE-TOKEN-HERE"
```

(Or `scp` from the Mac if you'd rather not type it.)

- [ ] **Step 5: Create `secrets.env` on the server**

```bash
ssh seattle "cd /home/nach/wapo-auto-login && cp secrets.env.example secrets.env"
```

- [ ] **Step 6: Ensure `nach` can run docker without sudo**

The systemd service runs as `nach`, so `nach` must be in the `docker` group; otherwise `run.sh` will fail on `docker run`.

```bash
ssh seattle "groups nach"
```

If the output does not include `docker`:

```bash
ssh seattle "sudo usermod -aG docker nach"
```

Group membership applies to new processes — exit and re-establish the SSH session so the next commands use the new group:

```bash
exit
ssh seattle "groups | tr ' ' '\n' | grep docker"
```

Expected: prints `docker`.

- [ ] **Step 7: Build the Docker image on the server**

```bash
ssh seattle "cd /home/nach/wapo-auto-login/docker && docker build -t wapo-renew:latest ."
```

Expected: build succeeds. (First build downloads the ~600MB base.)

- [ ] **Step 8: Manual smoke test on the server**

```bash
ssh seattle "cd /home/nach/wapo-auto-login && ./run.sh"
```

Expected: log line ending with `reauth-success` or `skip-still-active`. If fail, pull down the debug artifacts:

```bash
scp -r seattle:/home/nach/wapo-auto-login/debug/<latest>/ /tmp/wapo-debug/
playwright show-trace /tmp/wapo-debug/trace.zip
```

---

## Task 11: Enable the systemd timer

**Files:** none.

- [ ] **Step 1: Install the unit files**

```bash
ssh seattle <<'EOF'
sudo install -m 644 /home/nach/wapo-auto-login/systemd/wapo-renew.service /etc/systemd/system/wapo-renew.service
sudo install -m 644 /home/nach/wapo-auto-login/systemd/wapo-renew.timer /etc/systemd/system/wapo-renew.timer
sudo systemctl daemon-reload
EOF
```

- [ ] **Step 2: Manually trigger the service to verify systemd wiring**

```bash
ssh seattle "sudo systemctl start wapo-renew.service && sudo systemctl status wapo-renew.service --no-pager"
```

Expected: `Active: inactive (dead)` with `Process: ... ExecStart=/home/nach/wapo-auto-login/run.sh ... status=0/SUCCESS`.

Verify journald has the output:
```bash
ssh seattle "sudo journalctl -u wapo-renew.service --no-pager -n 20"
```

Expected: the same log line is in journald.

- [ ] **Step 3: Enable + start the timer**

```bash
ssh seattle "sudo systemctl enable --now wapo-renew.timer"
```

- [ ] **Step 4: Verify the timer is scheduled**

```bash
ssh seattle "systemctl list-timers wapo-renew.timer --no-pager"
```

Expected: shows next run at the next Mon or Fri 04:00 (+ random delay), `LAST` shows the manual run from Step 2.

---

## Task 12: README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# wapo-auto-login

Automated weekly re-authentication to The Washington Post via Seattle Public Library, running unattended on `seattle-server`.

## What it does

Every Monday and Friday at 04:00 (local time, +/- 2h jitter), `seattle-server` runs a headless Chromium that:

1. Loads `https://www.washingtonpost.com/subscribe/signin/special-offers/?s_oe=SPECIALOFFER_SEATTLEPL` using a persistent Chromium profile (cookies survive across runs).
2. If the WaPo sign-in form is visible, fills in email + password (two-step sign-in).
3. Waits for the activation API (`POST .../subscriptionapi/v2/subscriptions/special-offers`) to return 200 — that's the signal the entitlement was minted.

Logs land in `/home/nach/wapo-auto-login/renew.log` and in journald (`journalctl -u wapo-renew.service`). Failure artifacts (screenshot + DOM + Playwright trace) accumulate under `debug/`; only the most recent 5 are kept.

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
3. Install `op` CLI (v2.30+); create a 1P service account with read access to the vault holding the WaPo + SPL items.
4. Save the service account token to `~/.config/op/service-account-token`, mode 600.
5. `cd docker && sudo docker build -t wapo-renew:latest .`
6. Smoke test: `./run.sh` — should log `reauth-success` or `skip-still-active`.
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
- **CAPTCHA in the screenshot** → the bot can't solve it. Log in manually once on seattle-server (`ssh -X` + VNC into Xvfb, or wipe `profile/` and re-run from a desktop with screen sharing). Profile updates; next scheduled run resumes.
- **Selectors changed** → re-run Stage 1 recon on the Mac, update constants at the top of `docker/renew.py`, rebuild + redeploy.

## Local development

```
python3 -m venv .venv && source .venv/bin/activate
pip install pytest playwright
playwright install chromium
pytest                              # unit tests for utils.py
cd docker && docker build -t wapo-renew:latest . && cd ..
./run.sh                            # end-to-end against live SPL + WaPo
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Add README with deploy + troubleshooting docs"
```

---

## Task 13: Open the PR

Per user preference: end development work with a PR.

**Files:** none.

- [ ] **Step 1: Ensure branch is rebased on `main` (no-op here since spec is the only main commit and was the branch base)**

```bash
git fetch origin main
git log origin/main..HEAD --oneline   # should list every task's commit
```

- [ ] **Step 2: Push branch**

```bash
git push origin feat/initial-implementation
```

- [ ] **Step 3: Open the PR**

```bash
gh pr create --title "Initial implementation of WaPo auto-login" --body "$(cat <<'EOF'
## Summary
- Implements the design in `docs/superpowers/specs/2026-05-30-wapo-auto-login-design.md`
- Playwright (Python) in Docker, headful under Xvfb, persistent profile, probe-first idempotency
- systemd timer at `Mon,Fri 04:00` (3-4 day cadence, within 3-5d recommended window)
- Secrets resolved at runtime via 1Password `op run`; no creds on disk except the service account token (mode 600)

## Test plan
- [x] Unit tests pass: `pytest`
- [x] End-to-end smoke test on Mac: `./run.sh` re-authenticates from cold
- [x] Idempotency: second `./run.sh` exits with `skip-still-active`
- [x] Manual `systemctl start wapo-renew.service` on seattle-server succeeds
- [x] `systemctl list-timers` shows next Mon/Fri 04:00 schedule
- [ ] Wait for first scheduled run; confirm new entry in `renew.log`

Stage 1 recon notes in `recon/flow-notes.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: Wait for any CI / review comments (per `~/.claude/CLAUDE.md`)**

Even though this repo has no CI yet, wait a couple of minutes for any automated review (e.g., GitHub's Copilot review if enabled). Address comments before merging.

- [ ] **Step 5: Merge after approval**

```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 6: Pull `main` on seattle-server so it tracks the merged code**

```bash
ssh seattle "cd /home/nach/wapo-auto-login && git checkout main && git pull origin main"
```

(No rebuild needed unless `docker/` changed; in this case the merge to main is the same tree the branch already had on the server, so the deployed code is identical.)

---

## Task 14: Verify first scheduled run

This task waits for the next Monday or Friday 04:00 +/- 2h. **Skip until that time has passed.**

**Files:** none.

- [ ] **Step 1: Check timer status**

```bash
ssh seattle "systemctl list-timers wapo-renew.timer --no-pager && sudo journalctl -u wapo-renew.service --since '24 hours ago' --no-pager"
```

Expected: `LAST` column shows a recent run; journal has the new log line.

- [ ] **Step 2: Confirm `renew.log` has the new entry**

```bash
ssh seattle "tail -5 /home/nach/wapo-auto-login/renew.log"
```

Expected: most recent line is `ok\tskip-still-active\t...` (since the manual run from Task 11 left the entitlement active well within 4 days) OR `ok\treauth-success\t...` if enough time passed for it to lapse.

- [ ] **Step 3: Verify entitlement is still active in a real browser**

Visit `https://www.washingtonpost.com/` — no paywall.

Done. The system runs unattended until something breaks.

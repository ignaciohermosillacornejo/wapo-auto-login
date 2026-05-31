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
# Text WaPo shows on the special-offers page when the user already has an active
# entitlement; the activation API does not fire in this case.
ALREADY_SUBSCRIBED_TEXT = "Looks like you're already a subscriber"


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
        # Tracing is intentionally only persisted on the exception path
        # (see `dump_debug`). On a clean run, the trace is discarded — we
        # don't need to keep ~10 MB of artifacts for every successful run.
        ctx.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = ctx.new_page()

        try:
            page.goto(SPECIAL_OFFERS_URL, wait_until="domcontentloaded", timeout=30_000)

            # The page can land in one of two recognized states:
            #   1. Sign-in form visible — entitlement is lapsed (or cold profile);
            #      signing in triggers the activation API which mints a fresh one.
            #   2. "Looks like you're already a subscriber" — entitlement still active;
            #      no API call fires, nothing to do.
            email_input = page.get_by_role("textbox", name="Email address")
            already_subscribed = page.get_by_text(ALREADY_SUBSCRIBED_TEXT)
            email_input.or_(already_subscribed).first.wait_for(
                state="visible", timeout=20_000,
            )

            if already_subscribed.is_visible():
                duration = (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()
                log(status="ok", kind="skip-still-active", detail=f"duration={int(duration)}s")
                return 0

            # Sign-in path. Arm the activation-API waiter, then drive the form.
            # 120s budget = ~30s for goto + ~25s for two-step sign-in + slack
            # for a slow network round-trip to the activation API.
            with page.expect_response(
                lambda r: r.url == ACTIVATION_API_URL and r.status == 200,
                timeout=120_000,
            ) as response_info:
                sign_in_if_needed(
                    page, wapo_email=wapo_email, wapo_password=wapo_password,
                )
            response_info.value  # raises if the wait timed out

            duration = (datetime.datetime.now(datetime.timezone.utc) - started).total_seconds()
            log(status="ok", kind="reauth-success", detail=f"duration={int(duration)}s")
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
            ctx.close()


if __name__ == "__main__":
    sys.exit(main())

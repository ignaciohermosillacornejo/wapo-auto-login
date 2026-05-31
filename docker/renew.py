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
                lambda r: r.url == ACTIVATION_API_URL and r.status == 200,
                timeout=90_000,
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
            ctx.close()


if __name__ == "__main__":
    sys.exit(main())

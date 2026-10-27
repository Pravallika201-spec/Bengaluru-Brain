"""
Citizen registration OTP — backend structure only, no real SMS.

Mirrors this project's existing pattern for simulated delivery
(integration/alerts.py's send_sms_simulated(): the exact same idea, that
a real-provider seam should exist and be a drop-in swap later, without
ever pretending something was sent that wasn't). The OTP code is real
(generated with `secrets`, not `random`), really persisted, and really
checked with expiry/attempt limits -- only the SMS SEND step is absent.

DEV_MODE (env var CITIZEN_ALERTS_DEV_MODE, default "true"): while on, the
generated code is included directly in the API response (`dev_otp`) and
printed to the console, both clearly labeled. This project currently has
no SMS provider at all (per the Citizen Alert System Audit), so DEV_MODE
defaults on -- there is no other way to complete registration right now.
Turning it off does not add a real send path; it only stops exposing the
code, which would make verification impossible until a real provider is
wired in (future stage, explicitly not done here).
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

import citizen_registry as _registry

DEV_MODE = os.getenv("CITIZEN_ALERTS_DEV_MODE", "true").strip().lower() != "false"
OTP_TTL_SECONDS = 300
MAX_OTP_ATTEMPTS = 5
DEV_NOTICE = (
    "DEVELOPMENT MODE: no SMS provider is connected in this project. "
    "This code was NOT sent to any phone -- it is shown here only "
    "because CITIZEN_ALERTS_DEV_MODE is on."
)


def _mask(mobile_number: str) -> str:
    if len(mobile_number) <= 5:
        return "*" * len(mobile_number)
    return mobile_number[:3] + "*" * (len(mobile_number) - 5) + mobile_number[-2:]


def generate_otp(citizen_id, mobile_number: str, purpose: str = "registration") -> dict:
    """Generates, persists, and (dev-log only) prints a 6-digit code.
    Returns {"code", "expires_at"} -- callers decide whether `code` is
    safe to put in an HTTP response (only ever in DEV_MODE)."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    now = datetime.now()
    expires_at = now + timedelta(seconds=OTP_TTL_SECONDS)

    conn = _registry._connect()
    try:
        conn.execute(
            """
            INSERT INTO citizen_otp_requests (
                citizen_id, mobile_number, otp_code, purpose,
                created_at, expires_at, consumed, attempts
            ) VALUES (?, ?, ?, ?, ?, ?, 0, 0)
            """,
            (citizen_id, mobile_number, code, purpose, now.isoformat(), expires_at.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    print(
        f"[DEV OTP - NOT SENT VIA SMS] citizen_id={citizen_id} "
        f"mobile={_mask(mobile_number)} purpose={purpose} otp={code} "
        f"expires_in={OTP_TTL_SECONDS}s"
    )

    return {"code": code, "expires_at": expires_at.isoformat()}


def verify_otp(citizen_id, mobile_number: str, submitted_code: Optional[str],
                purpose: str = "registration") -> tuple[bool, str]:
    """Checks the most recent unconsumed OTP for (citizen_id, purpose)
    against submitted_code, honoring expiry and a max-attempts lockout.
    Returns (ok, reason)."""
    if not submitted_code or not str(submitted_code).strip():
        return False, "A verification code is required."

    conn = _registry._connect()
    try:
        row = conn.execute(
            """
            SELECT * FROM citizen_otp_requests
            WHERE citizen_id = ? AND purpose = ? AND consumed = 0
            ORDER BY id DESC LIMIT 1
            """,
            (citizen_id, purpose),
        ).fetchone()

        if row is None:
            return False, "No pending verification code for this account. Request a new one."

        if row["attempts"] >= MAX_OTP_ATTEMPTS:
            return False, "Too many incorrect attempts. Request a new verification code."

        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.now() > expires_at:
            return False, "Verification code expired. Request a new one."

        if not secrets.compare_digest(str(submitted_code).strip(), row["otp_code"]):
            conn.execute(
                "UPDATE citizen_otp_requests SET attempts = attempts + 1 WHERE id = ?",
                (row["id"],),
            )
            conn.commit()
            return False, "Incorrect verification code."

        conn.execute(
            "UPDATE citizen_otp_requests SET consumed = 1 WHERE id = ?",
            (row["id"],),
        )
        conn.commit()
        return True, "verified"
    finally:
        conn.close()

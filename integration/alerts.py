"""
Turns a USI result (from usi_engine.compute_usi) into a severity-appropriate
bilingual citizen alert (English + natural Kannada — composed as whole
sentences per band, not word-for-word translated) and a SIMULATED SMS send.

No real SMS provider is connected (per project rules: never send real SMS
or spend money on a provider unless explicitly requested). send_sms_simulated()
is the single seam where a real provider would plug in later — e.g.:

    def send_sms_real(phone_number, message):
        return twilio_client.messages.create(to=phone_number, body=message, from_=...)

and the caller in demo_usi_pipeline.py would swap the call — nothing else
in this module needs to change.
"""
import sys
from datetime import datetime

import alert_state

# Windows consoles often default to a legacy codepage (cp1252) that can't
# print Kannada (Unicode) characters — force UTF-8 stdout so the simulated
# SMS log actually prints instead of crashing.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# Kannada is composed per band as a natural sentence with the area name
# substituted in, not translated word-by-word from the English.
_TEMPLATES = {
    "Green": {
        "en": "Traffic and waste conditions in {area} are normal. No action needed.",
        "kn": "{area} ಪ್ರದೇಶದಲ್ಲಿ ಸಂಚಾರ ಮತ್ತು ತ್ಯಾಜ್ಯ ಪರಿಸ್ಥಿತಿ ಸಹಜವಾಗಿದೆ. ಯಾವುದೇ ಕ್ರಮ ಅಗತ್ಯವಿಲ್ಲ.",
    },
    "Yellow": {
        "en": "Caution: {area} is seeing rising traffic/waste risk ({reason}). Plan ahead if traveling through this area.",
        "kn": "ಎಚ್ಚರಿಕೆ: {area} ಪ್ರದೇಶದಲ್ಲಿ ಸಂಚಾರ/ತ್ಯಾಜ್ಯ ಅಪಾಯ ಹೆಚ್ಚುತ್ತಿದೆ ({reason}). ಈ ಪ್ರದೇಶದ ಮೂಲಕ ಪ್ರಯಾಣಿಸುವಾಗ ಮುಂಚಿತವಾಗಿ ಯೋಜಿಸಿ.",
    },
    "Orange": {
        "en": "Warning: {area} has elevated risk right now — {reason}. Avoid non-essential travel through this area if possible.",
        "kn": "ಎಚ್ಚರಿಕೆ: {area} ಪ್ರದೇಶದಲ್ಲಿ ಈಗ ಅಪಾಯ ಹೆಚ್ಚಾಗಿದೆ — {reason}. ಸಾಧ್ಯವಾದರೆ ಈ ಪ್ರದೇಶದ ಮೂಲಕ ಅನಗತ್ಯ ಪ್ರಯಾಣ ತಪ್ಪಿಸಿ.",
    },
    "Red": {
        "en": "Urgent: {area} is under severe combined risk — {reason}. Please avoid unnecessary travel and follow local advisories.",
        "kn": "ತುರ್ತು ಎಚ್ಚರಿಕೆ: {area} ಪ್ರದೇಶದಲ್ಲಿ ತೀವ್ರ ಅಪಾಯವಿದೆ — {reason}. ದಯವಿಟ್ಟು ಅನಗತ್ಯ ಪ್ರಯಾಣ ತಪ್ಪಿಸಿ ಮತ್ತು ಸ್ಥಳೀಯ ಸೂಚನೆಗಳನ್ನು ಅನುಸರಿಸಿ.",
    },
}


_LEVEL_KN = {"LOW": "ಕಡಿಮೆ", "MEDIUM": "ಮಧ್ಯಮ", "HIGH": "ಹೆಚ್ಚಿನ", "CRITICAL": "ತೀವ್ರ", "UNKNOWN": "ಅಜ್ಞಾತ"}


def _compose_reason_kn(usi_result):
    """Builds the Kannada reason as its own natural sentence fragment from
    the structured result — never by translating the English reason
    word-for-word."""
    parts = []
    t, w = usi_result["traffic"], usi_result["waste"]
    if t["score"] is not None:
        suffix = " (ಅಂದಾಜು)" if t["source"] == "SIMULATED_WARD_STRESS" else ""
        parts.append(f"{_LEVEL_KN.get(t['level'], t['level'])} ಸಂಚಾರ ದಟ್ಟಣೆ{suffix}")
    if w["score"] is not None:
        parts.append(f"{_LEVEL_KN.get(w['level'], w['level'])} ತ್ಯಾಜ್ಯ ಉಕ್ಕಿ ಹರಿಯುವ ಅಪಾಯ")
    reason_kn = " ಮತ್ತು ".join(parts) if parts else "ಸಾಕಷ್ಟು ಮಾಹಿತಿ ಇಲ್ಲ"
    if usi_result["compounding_bonus_applied"]:
        reason_kn += " — ಎರಡೂ ಏಕಕಾಲದಲ್ಲಿ ಹೆಚ್ಚಾಗಿರುವುದರಿಂದ ತ್ಯಾಜ್ಯ ವಾಹನಗಳ ಸಂಚಾರವೂ ಕಷ್ಟವಾಗಬಹುದು"
    return reason_kn


def classify_alert_type(usi_result):
    """Event-driven classification, independent of the overall band:
    HIGH+HIGH co-occurring is worse than either alone, and is called out
    explicitly rather than only being visible as a higher USI number."""
    t_level = usi_result["traffic"]["level"]
    w_level = usi_result["waste"]["level"]
    t_high = t_level in ("HIGH", "CRITICAL")
    w_high = w_level in ("HIGH", "CRITICAL")
    if t_high and w_high:
        return "URGENT_COMBINED"
    if t_high:
        return "TRAFFIC_ONLY"
    if w_high:
        return "WASTE_ONLY"
    return "GENERAL"


def generate_alert(usi_result):
    band = usi_result["band"]
    area = usi_result["area_name"]
    if band == "Unknown":
        return {
            "area": area,
            "band": band,
            "usi": usi_result.get("usi"),
            "alert_type": "NO_DATA",
            "timestamp": datetime.now().isoformat(),
            "english": f"No traffic or waste data is available for {area} right now.",
            "kannada": f"{area} ಪ್ರದೇಶಕ್ಕೆ ಸದ್ಯ ಯಾವುದೇ ಸಂಚಾರ ಅಥವಾ ತ್ಯಾಜ್ಯ ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ.",
        }

    template = _TEMPLATES[band]
    # English reason, lowercased for mid-sentence embedding
    reason_en = usi_result["reason"].rstrip(".")
    reason_en = reason_en[0].lower() + reason_en[1:] if reason_en else reason_en
    reason_kn = _compose_reason_kn(usi_result)
    return {
        "area": area,
        "band": band,
        "usi": usi_result["usi"],
        "alert_type": classify_alert_type(usi_result),
        "reason": usi_result["reason"],
        "timestamp": datetime.now().isoformat(),
        "english": template["en"].format(area=area, reason=reason_en),
        "kannada": template["kn"].format(area=area, reason=reason_kn),
    }


def send_sms_simulated(phone_number, alert):
    """Logs what WOULD be sent. Returns a result dict shaped like a real
    provider's response would be, so swapping in a real provider later is a
    drop-in replacement of this one function."""
    record = {
        "status": "SIMULATED_NOT_SENT",
        "to": phone_number,
        "band": alert["band"],
        "english": alert["english"],
        "kannada": alert["kannada"],
        "timestamp": datetime.now().isoformat(),
    }
    print(f"[SIMULATED SMS] to={phone_number} band={alert['band']}\n"
          f"  EN: {alert['english']}\n"
          f"  KN: {alert['kannada']}")
    return record


# Bands that should trigger a citizen alert at all (Green is informational
# only and, per the project spec, doesn't need to interrupt anyone).
ALERT_BANDS = {"Yellow", "Orange", "Red"}


def maybe_alert_and_send(usi_result, phone_number="+91-SIMULATED"):
    """Event-driven send with deduplication/cooldown (see alert_state.py):
    the same area won't re-alert at the same band more than once per
    COOLDOWN_MINUTES, UNLESS its USI has escalated rapidly, in which case
    it always fires (escalations must not be suppressed)."""
    if usi_result["band"] not in ALERT_BANDS:
        return None

    should_alert, dedup_tags, is_escalation = alert_state.check_and_update(
        usi_result["area_name"], usi_result.get("usi"), usi_result["band"]
    )
    alert = generate_alert(usi_result)
    if is_escalation:
        alert["alert_type"] = "ESCALATION"

    if not should_alert:
        return {
            "status": "SUPPRESSED_DEDUP",
            "to": phone_number,
            "band": alert["band"],
            "alert_type": alert["alert_type"],
            "dedup_reason": "; ".join(dedup_tags),
            "timestamp": datetime.now().isoformat(),
        }

    result = send_sms_simulated(phone_number, alert)
    result["alert_type"] = alert["alert_type"]
    if dedup_tags:
        result["notes"] = "; ".join(dedup_tags)
    return result

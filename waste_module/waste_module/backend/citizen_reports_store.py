"""
Lightweight, dependency-free citizen-report persistence.

The pre-existing backend/citizen_reporting_backend.py (Flask + SQLite) is
real code but cannot even import on this machine (flask_cors is not
installed) and nothing calls it. Rather than fight that dependency for a
feature that just needs simple append-only storage, this module reads/
writes a plain JSON file directly — no framework needed, importable from
both the Streamlit dashboard and integration/waste_signal.py.

This is REAL persistence: reports submitted through the dashboard are
written here and actually read back by the USI engine (see
integration/waste_signal.py's citizen-report escalation), not a no-op UI
mockup.
"""
import json
import os
import threading
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS_FILE = os.path.join(HERE, "data", "citizen_reports.json")
_lock = threading.Lock()


def _load():
    if not os.path.exists(REPORTS_FILE):
        return []
    try:
        with open(REPORTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(reports):
    os.makedirs(os.path.dirname(REPORTS_FILE), exist_ok=True)
    with open(REPORTS_FILE, "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)


def add_report(area_name, waste_type, severity, landmark="", description="",
               phone_number="", latitude=None, longitude=None):
    with _lock:
        reports = _load()
        report = {
            "id": len(reports) + 1,
            "area_name": area_name,
            "waste_type": waste_type,
            "severity": severity,
            "landmark": landmark,
            "description": description,
            "phone_number": phone_number,
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": datetime.now().isoformat(),
        }
        reports.append(report)
        _save(reports)
        return report


def get_recent_reports(limit=20):
    reports = _load()
    return list(reversed(reports))[:limit]


def get_reports_for_area(area_name, within_days=7):
    cutoff = datetime.now() - timedelta(days=within_days)
    reports = _load()
    norm = area_name.strip().lower()
    return [
        r for r in reports
        if r.get("area_name", "").strip().lower() == norm
        and datetime.fromisoformat(r["timestamp"]) >= cutoff
    ]


def get_report_counts_by_area(within_days=7):
    """area_name -> recent report count, for the USI citizen-escalation bonus."""
    cutoff = datetime.now() - timedelta(days=within_days)
    reports = _load()
    counts = {}
    for r in reports:
        try:
            ts = datetime.fromisoformat(r["timestamp"])
        except (KeyError, ValueError):
            continue
        if ts >= cutoff:
            key = r.get("area_name", "").strip()
            if key:
                counts[key] = counts.get(key, 0) + 1
    return counts

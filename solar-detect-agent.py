#!/usr/bin/env python3
"""
solar-detect-agent.py — Solar event detection and alerting for HOG.

Monitors public solar weather feeds (SWPC/NOAA), detects events,
tracks active regions, and generates alerts.

Commands:
  scan          — Fetch current solar conditions, report status
  flares        — Check for recent solar flares
  cme           — Check for coronal mass ejections
  geomag        — Check geomagnetic storm status (Kp index)
  regions       — List tracked active sunspot regions
  watch         — One-shot: scan + alert if anything significant
  history       — Show recent event history
"""
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from subprocess import run

STATE_DIR = Path(__file__).parent / "state"
STATE_DIR.mkdir(exist_ok=True)
HISTORY_FILE = STATE_DIR / "events.json"
DETECTION_CLIENT = Path(__file__).parent.parent.parent / "scripts" / "detection-client.py"

FEDERATION_REST = "http://localhost:8777"

# Public solar data endpoints (no API key needed)
SWPC_ALERTS = "https://services.swpc.noaa.gov/products/alerts.json"
SWPC_FLARE = "https://services.swpc.noaa.gov/json/goes/primary/xray-flares-7-day.json"
SWPC_KP = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"
SWPC_REGIONS = "https://services.swpc.noaa.gov/json/solar_regions.json"
SWPC_FLUX = "https://services.swpc.noaa.gov/json/f107_cm_flux.json"


def _fetch_json(url: str, timeout: int = 10) -> list | dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "EddieSolarDetect/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        return None


def _file_claim(summary: str, confidence: float, alert_type: str, evidence: dict | None = None) -> str | None:
    """File a detection claim to the federation coordination layer."""
    try:
        data = {
            "source": "solar-detect@hog",
            "domain": "solar",
            "summary": summary,
            "confidence": confidence,
            "evidence": {
                "alert_type": alert_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **(evidence or {}),
            },
            "ttl_seconds": 86400,  # 24h TTL for solar events
        }
        req = urllib.request.Request(
            f"{FEDERATION_REST}/detection/claim",
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
            return result.get("claim_id")
    except Exception as e:
        return None


def _save_event(event: dict):
    events = []
    if HISTORY_FILE.exists():
        try:
            events = json.loads(HISTORY_FILE.read_text())
        except:
            events = []
    events.append(event)
    # Keep last 200 events
    events = events[-200:]
    HISTORY_FILE.write_text(json.dumps(events, indent=2))


def cmd_scan() -> dict:
    """Full solar weather scan."""
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "conditions": {},
        "alerts": [],
    }

    # Kp index (geomagnetic activity)
    kp_data = _fetch_json(SWPC_KP)
    if kp_data and isinstance(kp_data, list) and len(kp_data) > 1:
        last = kp_data[-1]
        # Handle both list and dict formats
        if isinstance(last, dict):
            kp_val_str = str(last.get("kp", last.get("Kp", "0")))
            results["conditions"]["kp_forecast"] = {"raw": last}
        elif isinstance(last, (list, tuple)):
            kp_val_str = str(last[1]) if len(last) > 1 else "0"
            results["conditions"]["kp_forecast"] = {
                "time": last[0] if len(last) > 0 else None,
                "kp_value": last[1] if len(last) > 1 else None,
            }
        else:
            kp_val_str = "0"
        try:
            kp = float(kp_val_str)
            if kp >= 5:
                results["alerts"].append(f"GEOMAGNETIC_STORM: Kp={kp} (G{int(kp-4)} storm level)")
        except:
            pass

    # Active alerts
    alerts = _fetch_json(SWPC_ALERTS)
    if alerts and isinstance(alerts, list):
        recent = alerts[:5]
        results["conditions"]["recent_alerts"] = len(alerts)
        for a in recent[:3]:
            code = a.get("code", "")
            msg = a.get("message", "")[:200]
            results["alerts"].append(f"SWPC_{code}: {msg}")

    # Flare status
    flares = _fetch_json(SWPC_FLARE)
    if flares and isinstance(flares, list) and len(flares) > 0:
        last_flare = flares[-1]
        flare_class = last_flare.get("max_class", "?")
        results["conditions"]["last_flare"] = {
            "time": last_flare.get("max_time", "?"),
            "region": last_flare.get("flare_loc", "?"),
            "class": flare_class,
        }
        if flare_class.startswith("X"):
            results["alerts"].append(f"X-FLARE: Class {flare_class}")
        elif flare_class.startswith("M"):
            results["alerts"].append(f"M-FLARE: Class {flare_class}")

    results["alert_count"] = len(results["alerts"])
    results["status"] = "ALERT" if results["alerts"] else "QUIET"

    # File detection claims for significant events
    results["claims_filed"] = []
    for alert in results["alerts"]:
        alert_upper = alert.upper()
        if "X-FLARE" in alert_upper:
            claim_id = _file_claim(
                summary=f"X-class solar flare detected: {alert}",
                confidence=0.95,
                alert_type="x_flare",
                evidence=results["conditions"].get("last_flare"),
            )
            if claim_id:
                results["claims_filed"].append({"type": "x_flare", "claim_id": claim_id})
        elif "M-FLARE" in alert_upper:
            claim_id = _file_claim(
                summary=f"M-class solar flare detected: {alert}",
                confidence=0.85,
                alert_type="m_flare",
                evidence=results["conditions"].get("last_flare"),
            )
            if claim_id:
                results["claims_filed"].append({"type": "m_flare", "claim_id": claim_id})
        elif "GEOMAGNETIC" in alert_upper:
            claim_id = _file_claim(
                summary=f"Geomagnetic storm: {alert}",
                confidence=0.80,
                alert_type="geomagnetic_storm",
                evidence=results["conditions"].get("kp_forecast"),
            )
            if claim_id:
                results["claims_filed"].append({"type": "geomagnetic_storm", "claim_id": claim_id})
        elif "SWPC_" in alert_upper:
            # Generic SWPC alerts — file with lower confidence
            claim_id = _file_claim(
                summary=f"SWPC alert: {alert[:200]}",
                confidence=0.70,
                alert_type="swpc_alert",
                evidence={"alert_snippet": alert[:500]},
            )
            if claim_id:
                results["claims_filed"].append({"type": "swpc_alert", "claim_id": claim_id})

    # Save scan
    _save_event(results)
    return results


def cmd_flares() -> dict:
    """Check recent solar flares."""
    flares = _fetch_json(SWPC_FLARE)
    if not flares or not isinstance(flares, list):
        return {"error": "Could not fetch flare data"}

    recent = flares[-10:]
    flare_list = []
    for f in recent:
        if isinstance(f, dict):
            flare_list.append({
                "time": f.get("max_time", "?"),
                "region": f.get("flare_loc", "?"),
                "class": f.get("max_class", "?"),
            })

    significant = [f for f in flare_list if f.get("class", "").startswith(("X", "M"))]

    return {
        "recent_flares": flare_list,
        "significant": significant,
        "total": len(flares),
        "status": "ALERT" if significant else "QUIET",
    }


def cmd_cme() -> dict:
    """Check for CME-related alerts."""
    alerts = _fetch_json(SWPC_ALERTS)
    if not alerts:
        return {"error": "Could not fetch alerts"}

    cme_alerts = [a for a in alerts if "CME" in a.get("message", "").upper()]
    return {
        "cme_alerts": len(cme_alerts),
        "recent": [{"code": a.get("code"), "summary": a.get("message", "")[:300]} for a in cme_alerts[:5]],
    }


def cmd_geomag() -> dict:
    """Check geomagnetic conditions."""
    kp_data = _fetch_json(SWPC_KP)
    if not kp_data or not isinstance(kp_data, list):
        return {"error": "Could not fetch Kp data"}

    latest = kp_data[-1] if kp_data else None
    kp_val = None
    if isinstance(latest, dict):
        kp_val = latest.get("kp")
        time_tag = latest.get("time_tag")
    elif isinstance(latest, (list, tuple)):
        kp_val = latest[1] if len(latest) > 1 else None
        time_tag = latest[0] if len(latest) > 0 else None
    else:
        time_tag = None

    try:
        kp_val = float(kp_val) if kp_val is not None else None
    except:
        kp_val = None

    storm_level = None
    if kp_val and kp_val >= 5:
        storm_level = f"G{int(kp_val - 4)}"

    return {
        "kp_index": kp_val,
        "storm_level": storm_level,
        "time": time_tag,
        "status": "STORM" if storm_level else "QUIET",
    }


def cmd_regions() -> dict:
    """List tracked sunspot regions."""
    regions = _fetch_json(SWPC_REGIONS)
    if not regions or not isinstance(regions, list):
        return {"error": "Could not fetch region data"}

    # Latest observed date
    latest_date = None
    if regions and isinstance(regions[-1], dict):
        latest_date = regions[-1].get("observed_date")

    # Filter to latest date only
    latest_regions = [r for r in regions if isinstance(r, dict) and r.get("observed_date") == latest_date]

    return {
        "active_regions": len(latest_regions),
        "date": latest_date,
        "regions": latest_regions[:10],
        "status": "OK",
    }


def cmd_watch() -> dict:
    """One-shot watch — scan and alert if anything notable."""
    scan = cmd_scan()
    
    critical = [a for a in scan.get("alerts", []) 
                if any(k in a.upper() for k in ["X-FLARE", "GEOMAGNETIC", "CME"])]
    
    if critical:
        return {
            "status": "CRITICAL",
            "alerts": critical,
            "timestamp": scan["timestamp"],
        }
    elif scan.get("alerts"):
        return {
            "status": "WATCH",
            "alerts": scan["alerts"],
            "timestamp": scan["timestamp"],
        }
    return {"status": "QUIET", "timestamp": scan["timestamp"]}


def cmd_history() -> dict:
    """Show recent event history."""
    if not HISTORY_FILE.exists():
        return {"events": [], "total": 0}
    events = json.loads(HISTORY_FILE.read_text())
    return {"events": events[-10:], "total": len(events)}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    commands = {
        "scan": cmd_scan,
        "flares": cmd_flares,
        "cme": cmd_cme,
        "geomag": cmd_geomag,
        "regions": cmd_regions,
        "watch": cmd_watch,
        "history": cmd_history,
    }

    if cmd not in commands:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

    result = commands[cmd]()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
data-detect-agent.py — Data pipeline health & anomaly detection for HOG.

Monitors data sources, detects stale/missing/drifted data, schema changes,
and alerts when things look wrong.

Commands:
  scan              — Scan all known data sources, report health
  check <source>    — Deep check a specific source
  baseline <source> — Capture current state as baseline for drift detection
  watch             — One-shot watch: scan + alert if anything wrong
  sources           — List all known data sources
  history <source>  — Show check history for a source
"""
import json
import os
import hashlib
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path(__file__).parent / "state"
STATE_DIR.mkdir(exist_ok=True)
BASELINES = STATE_DIR / "baselines"
BASELINES.mkdir(exist_ok=True)
HISTORY = STATE_DIR / "history"
HISTORY.mkdir(exist_ok=True)

WORKSPACE = Path("/home/marvin/.openclaw/workspace")
DATA_DIR = WORKSPACE / "data"
FEDERATION_REST = "http://localhost:8777"

# Known data sources on HOG
# active = should be refreshed by cron; dormant = legacy/archival, not expected to change
SOURCES = {
    "bootstrap-live": {"path": WORKSPACE / "BOOTSTRAP.md", "active": True, "max_age": 30},
    "eddie-atlas": {"path": Path("/home/marvin/.openclaw/workspace/data/manifold/eddie-atlas.json"), "active": True, "max_age": 60},
    "clawstreet-credentials": {"path": DATA_DIR / "clawstreet-credentials.json", "active": False},
    "clawstreet-stoploss-state": {"path": DATA_DIR / "clawstreet-stoploss-state.json", "active": False},
    "clawstreet-stoploss-log": {"path": DATA_DIR / "clawstreet-stoploss-log.jsonl", "active": False},
    "poreee-monitor-state": {"path": DATA_DIR / "poreee" / "monitor-state.json", "active": False},
    "poreee-blocks": {"path": DATA_DIR / "poreee" / "blocks.md", "active": False},
    "injection-audit": {"path": DATA_DIR / "injection-audit", "active": False},
    "mev-wallet": {"path": DATA_DIR / "mev", "active": False},
    "alerts": {"path": DATA_DIR / "alerts", "active": False},
}


def _file_claim(summary: str, confidence: float, issue_type: str, source: str, evidence: dict | None = None) -> str | None:
    """File a detection claim to the federation coordination layer."""
    try:
        data = {
            "source": "data-detect@hog",
            "domain": "data_pipeline",
            "summary": summary,
            "confidence": confidence,
            "evidence": {
                "issue_type": issue_type,
                "source_name": source,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **(evidence or {}),
            },
            "ttl_seconds": 3600,  # 1h TTL for data pipeline issues
        }
        req = urllib.request.Request(
            f"{FEDERATION_REST}/detection/claim",
            data=json.dumps(data).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
            return result.get("claim_id")
    except Exception:
        return None


def _file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    if path.is_dir():
        h = hashlib.md5()
        for f in sorted(path.rglob("*")):
            if f.is_file():
                h.update(f.read_bytes())
        return h.hexdigest()
    return hashlib.md5(path.read_bytes()).hexdigest()


def _file_age_minutes(path: Path) -> float | None:
    if not path.exists():
        return None
    if path.is_dir():
        files = list(path.rglob("*"))
        if not files:
            return None
        mtimes = [f.stat().st_mtime for f in files if f.is_file()]
        if not mtimes:
            return None
        return (datetime.now().timestamp() - max(mtimes)) / 60
    return (datetime.now().timestamp() - path.stat().st_mtime) / 60


def _file_size_kb(path: Path) -> float | None:
    if not path.exists():
        return None
    if path.is_dir():
        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return total / 1024
    return path.stat().st_size / 1024


def _check_source(name: str, info: dict) -> dict:
    path = info["path"] if isinstance(info, dict) else info
    active = info.get("active", True) if isinstance(info, dict) else True
    max_age = info.get("max_age", 1440) if isinstance(info, dict) else 1440
    
    exists = path.exists()
    result = {
        "source": name,
        "path": str(path),
        "exists": exists,
        "active": active,
        "healthy": True,
        "issues": [],
    }

    if not exists:
        result["healthy"] = False
        result["issues"].append("MISSING — file/directory not found")
        return result

    age = _file_age_minutes(path)
    size = _file_size_kb(path)
    hsh = _file_hash(path)

    result["age_minutes"] = round(age, 1) if age is not None else None
    result["size_kb"] = round(size, 2) if size is not None else None
    result["hash"] = hsh

    # Only staleness-check active sources
    if active and age is not None and age > max_age:
        result["healthy"] = False
        result["issues"].append(f"STALE — {age:.0f}min old (max {max_age}min)")

    # Empty file check
    if size is not None and size == 0:
        result["healthy"] = False
        result["issues"].append("EMPTY — zero bytes")

    # Drift check against baseline
    baseline_path = BASELINES / f"{name}.json"
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text())
        if hsh and baseline.get("hash") and hsh != baseline["hash"]:
            result["changed_since_baseline"] = True
            result["baseline_age_minutes"] = baseline.get("age_minutes")
        else:
            result["changed_since_baseline"] = False

    # JSON validity check for .json files
    if exists and not path.is_dir() and str(path).endswith(".json"):
        try:
            json.loads(path.read_text())
        except json.JSONDecodeError as e:
            result["healthy"] = False
            result["issues"].append(f"CORRUPT — invalid JSON: {e}")

    return result


def cmd_scan() -> dict:
    results = []
    for name, info in SOURCES.items():
        r = _check_source(name, info)
        results.append(r)
    
    healthy = sum(1 for r in results if r["healthy"])
    total = len(results)
    
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources_checked": total,
        "healthy": healthy,
        "unhealthy": total - healthy,
        "results": results,
    }

    # Save to history
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    (HISTORY / f"scan-{ts}.json").write_text(json.dumps(report, indent=2))

    # File detection claims for unhealthy sources
    report["claims_filed"] = []
    for r in results:
        if not r["healthy"] and r["active"]:
            for issue in r["issues"]:
                issue_type = issue.split("—")[0].strip() if "—" in issue else "unknown"
                confidence = 0.9 if "MISSING" in issue else 0.7 if "STALE" in issue else 0.6
                claim_id = _file_claim(
                    summary=f"{r['source']}: {issue}",
                    confidence=confidence,
                    issue_type=issue_type,
                    source=r["source"],
                    evidence={"age_minutes": r.get("age_minutes"), "issues": r["issues"]},
                )
                if claim_id:
                    report["claims_filed"].append({"source": r["source"], "issue": issue_type, "claim_id": claim_id})

    return report


def cmd_check(source: str) -> dict:
    if source not in SOURCES:
        # Try partial match
        matches = [s for s in SOURCES if source in s]
        if len(matches) == 1:
            source = matches[0]
        else:
            return {"error": f"Unknown source '{source}'. Known: {list(SOURCES.keys())}"}
    
    return _check_source(source, SOURCES[source])


def cmd_baseline(source: str) -> dict:
    if source not in SOURCES:
        return {"error": f"Unknown source '{source}'"}
    
    info = SOURCES[source]
    path = info["path"] if isinstance(info, dict) else info
    r = _check_source(source, info)
    baseline_path = BASELINES / f"{source}.json"
    baseline_path.write_text(json.dumps(r, indent=2))
    
    return {"action": "baseline_captured", "source": source, "state": r}


def cmd_watch() -> dict:
    scan = cmd_scan()
    issues = []
    for r in scan["results"]:
        if not r["healthy"]:
            issues.extend([f"{r['source']}: {i}" for i in r["issues"]])
    
    if issues:
        return {
            "status": "ALERT",
            "issues": issues,
            "timestamp": scan["timestamp"],
        }
    return {"status": "OK", "timestamp": scan["timestamp"], "sources": scan["sources_checked"]}


def cmd_sources() -> dict:
    return {
        "sources": [
            {
                "name": n,
                "path": str(info["path"] if isinstance(info, dict) else info),
                "exists": (info["path"] if isinstance(info, dict) else info).exists(),
                "active": info.get("active", True) if isinstance(info, dict) else True,
            }
            for n, info in SOURCES.items()
        ]
    }


def cmd_history(source: str) -> dict:
    if source not in SOURCES:
        return {"error": f"Unknown source '{source}'"}
    
    scans = sorted(HISTORY.glob("scan-*.json"), reverse=True)[:10]
    history = []
    for sf in scans:
        data = json.loads(sf.read_text())
        for r in data.get("results", []):
            if r["source"] == source:
                history.append({
                    "timestamp": data["timestamp"],
                    "healthy": r["healthy"],
                    "issues": r.get("issues", []),
                    "age_minutes": r.get("age_minutes"),
                })
    
    return {"source": source, "checks": history}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    commands = {
        "scan": lambda: cmd_scan(),
        "check": lambda: cmd_check(args[0]) if args else {"error": "specify source"},
        "baseline": lambda: cmd_baseline(args[0]) if args else {"error": "specify source"},
        "watch": lambda: cmd_watch(),
        "sources": lambda: cmd_sources(),
        "history": lambda: cmd_history(args[0]) if args else {"error": "specify source"},
    }

    if cmd not in commands:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)

    result = commands[cmd]()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

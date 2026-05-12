"""
Timeseries query — reads recorder JSONL files from the fog-event-relay.

The relay's recorder writes JSONL files (one per day) with all fog events.
This module queries them for historical analysis.

Expected file layout:
    fog-data/
        2026-05-04.jsonl
        2026-05-03.jsonl
        ...

Each line is a JSON event matching FogEvent format.
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional

from .types import EventType, FogEvent

# Default data directory (relative to relay or configurable)
DEFAULT_DATA_DIR = "fog-data"


@dataclass(frozen=True)
class TimeseriesEntry:
    """A timeseries point — event + sequence metadata."""
    event: FogEvent
    sequence: int          # line number in the JSONL file
    file: str              # source file name

    @property
    def timestamp(self) -> datetime:
        return self.event.timestamp


def query_timeseries(
    from_ts: datetime,
    to_ts: Optional[datetime] = None,
    *,
    event_types: Optional[List[str]] = None,
    data_dir: str = DEFAULT_DATA_DIR,
    limit: int = 1000,
) -> List[TimeseriesEntry]:
    """
    Query recorded fog events within a time range.

    Args:
        from_ts: Start of range (inclusive).
        to_ts: End of range (inclusive). Defaults to now.
        event_types: Filter to these event types. None = all types.
        data_dir: Directory containing daily JSONL files.
        limit: Max events to return.

    Returns:
        List of TimeseriesEntry, ordered by timestamp ascending.
    """
    if to_ts is None:
        to_ts = datetime.now(timezone.utc)

    # Normalize to UTC
    if from_ts.tzinfo is None:
        from_ts = from_ts.replace(tzinfo=timezone.utc)
    if to_ts.tzinfo is None:
        to_ts = to_ts.replace(tzinfo=timezone.utc)

    # Determine which daily files to read
    type_filter = None
    if event_types:
        type_filter = {EventType(et) for et in event_types}

    entries: List[TimeseriesEntry] = []
    data_path = Path(data_dir)

    # Walk from from_ts to to_ts, one day at a time
    current_day = from_ts.date()
    end_day = to_ts.date()

    while current_day <= end_day and len(entries) < limit:
        filename = f"{current_day.isoformat()}.jsonl"
        filepath = data_path / filename

        if filepath.exists():
            day_entries = _read_jsonl(
                filepath,
                from_ts=from_ts if current_day == from_ts.date() else None,
                to_ts=to_ts if current_day == end_day else None,
                type_filter=type_filter,
                limit=limit - len(entries),
            )
            entries.extend(day_entries)

        current_day += timedelta(days=1)

    return entries


def _read_jsonl(
    filepath: Path,
    *,
    from_ts: Optional[datetime] = None,
    to_ts: Optional[datetime] = None,
    type_filter: Optional[set] = None,
    limit: int = 1000,
) -> List[TimeseriesEntry]:
    """Read and filter events from a single JSONL file."""
    entries: List[TimeseriesEntry] = []

    try:
        with open(filepath, "r") as f:
            for seq, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Parse event
                try:
                    event = FogEvent.from_dict(payload)
                except (KeyError, ValueError):
                    continue

                # Apply filters
                if type_filter and event.type not in type_filter:
                    continue

                if from_ts and event.timestamp < from_ts:
                    continue
                if to_ts and event.timestamp > to_ts:
                    continue

                entries.append(TimeseriesEntry(
                    event=event,
                    sequence=seq,
                    file=filepath.name,
                ))

                if len(entries) >= limit:
                    break
    except FileNotFoundError:
        pass

    return entries

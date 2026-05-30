"""Logg alle varsler og rapporter til journal.jsonl for etterprøving."""
import json
import datetime
import pathlib

JOURNAL_PATH = pathlib.Path("journal.jsonl")


def log_entry(event_type: str, ticker: str, payload: dict) -> None:
    entry = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "type": event_type,
        "ticker": ticker,
        **payload,
    }
    with JOURNAL_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_recent(event_type: str, ticker: str, hours: float) -> list[dict]:
    """Returner oppføringer for ticker de siste N timene."""
    if not JOURNAL_PATH.exists():
        return []
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    results = []
    with JOURNAL_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != event_type or entry.get("ticker") != ticker:
                continue
            ts = datetime.datetime.fromisoformat(entry["ts"].rstrip("Z"))
            if ts >= cutoff:
                results.append(entry)
    return results

from typing import Any, Dict
from . import db

DEFAULTS: Dict[str, Any] = {
    "poll_interval_seconds": 30,
    "size_poll_interval_seconds": 300,
    "retention_days": 30,
}


def get_all() -> Dict[str, Any]:
    out = dict(DEFAULTS)
    with db.get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    for row in rows:
        key = row["key"]
        if key in DEFAULTS:
            try:
                out[key] = type(DEFAULTS[key])(row["value"])
            except (TypeError, ValueError):
                pass
    return out


def get(key: str) -> Any:
    return get_all().get(key, DEFAULTS.get(key))


def set_many(values: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, raw in values.items():
        if key not in DEFAULTS:
            continue
        try:
            coerced = type(DEFAULTS[key])(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(coerced, int) and coerced < 1:
            continue
        clean[key] = coerced
    with db.get_conn() as conn:
        for key, value in clean.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )
    return get_all()

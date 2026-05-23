from typing import Any, Dict
from . import db

DEFAULTS: Dict[str, Any] = {
    "poll_interval_seconds": 30,
    "size_poll_interval_seconds": 300,
    "retention_days": 30,
    "enabled": True,
}


def _coerce(default: Any, raw: Any) -> Any:
    """Coerce ``raw`` to the type of ``default``. Returns None if not possible."""
    if isinstance(default, bool):
        # NOTE: bool is a subclass of int, so this check must come first.
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        if isinstance(raw, str):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        return None
    try:
        return type(default)(raw)
    except (TypeError, ValueError):
        return None


def get_all() -> Dict[str, Any]:
    out = dict(DEFAULTS)
    with db.get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    for row in rows:
        key = row["key"]
        if key in DEFAULTS:
            coerced = _coerce(DEFAULTS[key], row["value"])
            if coerced is not None:
                out[key] = coerced
    return out


def get(key: str) -> Any:
    return get_all().get(key, DEFAULTS.get(key))


def set_many(values: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, raw in values.items():
        if key not in DEFAULTS:
            continue
        coerced = _coerce(DEFAULTS[key], raw)
        if coerced is None:
            continue
        # Positive-int settings: reject zero/negatives. bool slips through because
        # True/False round-trip cleanly through int(1)/int(0).
        if isinstance(DEFAULTS[key], int) and not isinstance(DEFAULTS[key], bool):
            if coerced < 1:
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

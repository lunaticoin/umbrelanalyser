import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, export, settings
from .collector import collector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("umbrelanalyser")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    await collector.start()
    try:
        yield
    finally:
        await collector.stop()


app = FastAPI(title="Umbrel Analyser", lifespan=lifespan)


# ----------- static / pages -----------

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index_page() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/container.html", include_in_schema=False)
def container_page() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "container.html"))


@app.get("/settings.html", include_in_schema=False)
def settings_page() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "settings.html"))


# ----------- API -----------

@app.get("/api/health")
def health() -> Dict[str, Any]:
    with db.get_conn() as conn:
        s = db.db_stats(conn)
    return {
        "ok": True,
        "now": db.now_ts(),
        "last_stats_ok": collector.last_stats_ok,
        "last_size_ok": collector.last_size_ok,
        "last_error": collector.last_error,
        "db": s,
    }


@app.get("/api/containers")
def list_containers() -> List[Dict[str, Any]]:
    with db.get_conn() as conn:
        containers = db.list_containers(conn)
        out = []
        for c in containers:
            latest = db.latest_sample(conn, c["container_id"])
            size = db.latest_size_sample(conn, c["container_id"])
            out.append({
                "id": c["container_id"],
                "short_id": c["container_id"][:12],
                "name": c["name"],
                "image": c["image"],
                "first_seen": c["first_seen"],
                "last_seen": c["last_seen"],
                "latest": dict(latest) if latest else None,
                "latest_size": dict(size) if size else None,
            })
    return out


@app.get("/api/containers/{container_id}")
def get_container(container_id: str) -> Dict[str, Any]:
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM containers WHERE container_id = ? OR container_id LIKE ?",
            (container_id, container_id + "%"),
        ).fetchone()
        if not row:
            raise HTTPException(404, "container not found")
        latest = db.latest_sample(conn, row["container_id"])
        size = db.latest_size_sample(conn, row["container_id"])
    return {
        "id": row["container_id"],
        "name": row["name"],
        "image": row["image"],
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
        "latest": dict(latest) if latest else None,
        "latest_size": dict(size) if size else None,
    }


def _resolve_range(ts_from: Optional[int], ts_to: Optional[int], hours: Optional[int]) -> tuple[int, int]:
    now = db.now_ts()
    if hours is not None and ts_from is None and ts_to is None:
        ts_to = now
        ts_from = 0 if hours == 0 else now - hours * 3600
    if ts_from is None:
        ts_from = now - 24 * 3600
    if ts_to is None:
        ts_to = now
    if ts_from > ts_to:
        ts_from, ts_to = ts_to, ts_from
    return ts_from, ts_to


def _resolve_container_id(conn, container_id: str) -> str:
    row = conn.execute(
        "SELECT container_id FROM containers WHERE container_id = ? OR container_id LIKE ?",
        (container_id, container_id + "%"),
    ).fetchone()
    if not row:
        raise HTTPException(404, "container not found")
    return row["container_id"]


@app.get("/api/containers/{container_id}/metrics")
def metrics(
    container_id: str,
    ts_from: Optional[int] = Query(None, alias="from"),
    ts_to: Optional[int] = Query(None, alias="to"),
    hours: Optional[int] = Query(None, ge=0, le=24 * 365),
) -> Dict[str, Any]:
    ts_from, ts_to = _resolve_range(ts_from, ts_to, hours)
    with db.get_conn() as conn:
        cid = _resolve_container_id(conn, container_id)
        samples = db.samples_range(conn, cid, ts_from, ts_to)
        sizes = db.size_samples_range(conn, cid, ts_from, ts_to)
    return {
        "container_id": cid,
        "range": {"from": ts_from, "to": ts_to},
        "samples": [dict(r) for r in samples],
        "size_samples": [dict(r) for r in sizes],
    }


@app.get("/api/containers/{container_id}/export.csv")
def export_csv(
    container_id: str,
    ts_from: Optional[int] = Query(None, alias="from"),
    ts_to: Optional[int] = Query(None, alias="to"),
    hours: Optional[int] = Query(None, ge=0, le=24 * 365),
    kind: str = Query("samples", pattern="^(samples|sizes)$"),
) -> Response:
    ts_from, ts_to = _resolve_range(ts_from, ts_to, hours)
    with db.get_conn() as conn:
        cid = _resolve_container_id(conn, container_id)
        cont = conn.execute(
            "SELECT * FROM containers WHERE container_id = ?", (cid,)
        ).fetchone()
        if kind == "samples":
            rows = db.samples_range(conn, cid, ts_from, ts_to)
            csv_text = export.rows_to_csv((dict(r) for r in rows), export.SAMPLE_FIELDS)
        else:
            rows = db.size_samples_range(conn, cid, ts_from, ts_to)
            csv_text = export.rows_to_csv((dict(r) for r in rows), export.SIZE_FIELDS)
    safe_name = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in cont["name"])
    filename = f"{safe_name}_{kind}_{ts_from}_{ts_to}.csv"
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/containers/{container_id}/export.json")
def export_json(
    container_id: str,
    ts_from: Optional[int] = Query(None, alias="from"),
    ts_to: Optional[int] = Query(None, alias="to"),
    hours: Optional[int] = Query(None, ge=0, le=24 * 365),
) -> Response:
    ts_from, ts_to = _resolve_range(ts_from, ts_to, hours)
    with db.get_conn() as conn:
        cid = _resolve_container_id(conn, container_id)
        cont = conn.execute(
            "SELECT * FROM containers WHERE container_id = ?", (cid,)
        ).fetchone()
        samples = db.samples_range(conn, cid, ts_from, ts_to)
        sizes = db.size_samples_range(conn, cid, ts_from, ts_to)
    body = export.rows_to_json(dict(cont), [dict(r) for r in samples], [dict(r) for r in sizes], ts_from, ts_to)
    safe_name = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in cont["name"])
    filename = f"{safe_name}_{ts_from}_{ts_to}.json"
    return Response(
        body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---- global export ----

@app.get("/api/export/all.csv")
def export_all_csv(
    ts_from: Optional[int] = Query(None, alias="from"),
    ts_to: Optional[int] = Query(None, alias="to"),
    hours: Optional[int] = Query(None, ge=0, le=24 * 365),
    kind: str = Query("samples", pattern="^(samples|sizes)$"),
) -> Response:
    ts_from, ts_to = _resolve_range(ts_from, ts_to, hours)
    with db.get_conn() as conn:
        if kind == "samples":
            rows = db.samples_range_all(conn, ts_from, ts_to)
            fields = export.SAMPLE_FIELDS_ALL
        else:
            rows = db.size_samples_range_all(conn, ts_from, ts_to)
            fields = export.SIZE_FIELDS_ALL
        csv_text = export.rows_to_csv((dict(r) for r in rows), fields)
    filename = f"umbrelanalyser_all_{kind}_{ts_from}_{ts_to}.csv"
    return PlainTextResponse(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/export/all.json")
def export_all_json(
    ts_from: Optional[int] = Query(None, alias="from"),
    ts_to: Optional[int] = Query(None, alias="to"),
    hours: Optional[int] = Query(None, ge=0, le=24 * 365),
) -> Response:
    ts_from, ts_to = _resolve_range(ts_from, ts_to, hours)
    with db.get_conn() as conn:
        containers = [dict(c) for c in db.list_containers(conn)]
        samples_rows = db.samples_range_all(conn, ts_from, ts_to)
        sizes_rows = db.size_samples_range_all(conn, ts_from, ts_to)
    samples_by_cid: Dict[str, list] = {}
    for r in samples_rows:
        samples_by_cid.setdefault(r["container_id"], []).append(dict(r))
    sizes_by_cid: Dict[str, list] = {}
    for r in sizes_rows:
        sizes_by_cid.setdefault(r["container_id"], []).append(dict(r))
    body = export.all_to_json(containers, samples_by_cid, sizes_by_cid, ts_from, ts_to)
    filename = f"umbrelanalyser_all_{ts_from}_{ts_to}.json"
    return Response(
        body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---- settings ----

class SettingsPayload(BaseModel):
    poll_interval_seconds: Optional[int] = None
    size_poll_interval_seconds: Optional[int] = None
    retention_days: Optional[int] = None


@app.get("/api/settings")
def get_settings() -> Dict[str, Any]:
    return settings.get_all()


@app.post("/api/settings")
def post_settings(payload: SettingsPayload) -> Dict[str, Any]:
    values = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not values:
        return settings.get_all()
    return settings.set_many(values)

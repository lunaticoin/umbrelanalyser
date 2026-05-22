import asyncio
import logging
import os
from typing import Any, Dict, Optional

from . import db, docker_client, settings

log = logging.getLogger(__name__)

# Cap parallelism per poll so we don't hammer the Docker socket
_STATS_CONCURRENCY = 6
_SIZE_CONCURRENCY = 2


class Collector:
    def __init__(self) -> None:
        self._prev_cpu: Dict[str, Dict[str, Any]] = {}
        self._stop = asyncio.Event()
        self._stats_task: Optional[asyncio.Task] = None
        self._size_task: Optional[asyncio.Task] = None
        self._prune_task: Optional[asyncio.Task] = None
        self.last_stats_ok: Optional[int] = None
        self.last_size_ok: Optional[int] = None
        self.last_error: Optional[str] = None

    # ---------------- public ----------------

    async def start(self) -> None:
        self._stop.clear()
        self._stats_task = asyncio.create_task(self._loop_stats(), name="collector-stats")
        self._size_task = asyncio.create_task(self._loop_sizes(), name="collector-sizes")
        self._prune_task = asyncio.create_task(self._loop_prune(), name="collector-prune")
        log.info("collector started")

    async def stop(self) -> None:
        self._stop.set()
        for t in (self._stats_task, self._size_task, self._prune_task):
            if t:
                t.cancel()
        for t in (self._stats_task, self._size_task, self._prune_task):
            if t:
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        log.info("collector stopped")

    # ---------------- stats loop ----------------

    async def _loop_stats(self) -> None:
        while not self._stop.is_set():
            interval = max(5, int(settings.get("poll_interval_seconds")))
            try:
                await asyncio.to_thread(self._collect_stats_once)
                self.last_stats_ok = db.now_ts()
                self.last_error = None
            except Exception as e:
                self.last_error = f"stats: {e}"
                log.exception("stats collection failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    def _collect_stats_once(self) -> None:
        client = docker_client.get_client()
        try:
            containers = docker_client.list_running_containers(client)
        finally:
            pass

        sem_count = min(_STATS_CONCURRENCY, max(1, len(containers)))
        from concurrent.futures import ThreadPoolExecutor

        ts = db.now_ts()
        results = []
        with ThreadPoolExecutor(max_workers=sem_count) as ex:
            futures = {ex.submit(docker_client.get_stats, client, c["id"]): c for c in containers}
            for fut in futures:
                c = futures[fut]
                try:
                    stats = fut.result()
                except Exception as e:
                    log.warning("stats fut failed %s: %s", c["name"], e)
                    stats = None
                if stats is None:
                    continue
                results.append((c, stats))

        with db.get_conn() as conn:
            for c, stats in results:
                db.upsert_container(conn, c["id"], c["name"], c["image"], ts)
                prev = self._prev_cpu.get(c["id"])
                cpu_pct = docker_client.parse_cpu_percent(stats, prev)
                self._prev_cpu[c["id"]] = stats
                mem = docker_client.parse_mem(stats)
                blk = docker_client.parse_blkio(stats)
                net = docker_client.parse_net(stats)
                db.insert_sample(
                    conn,
                    ts=ts,
                    container_id=c["id"],
                    cpu_percent=cpu_pct,
                    mem_bytes=mem["bytes"],
                    mem_limit_bytes=mem["limit"],
                    mem_percent=mem["percent"],
                    blk_read_bytes=blk["read"],
                    blk_write_bytes=blk["write"],
                    net_rx_bytes=net["rx"],
                    net_tx_bytes=net["tx"],
                )

        # forget cpu state for containers that have disappeared
        live_ids = {c["id"] for c, _ in results}
        for cid in list(self._prev_cpu.keys()):
            if cid not in live_ids:
                self._prev_cpu.pop(cid, None)

    # ---------------- size loop ----------------

    async def _loop_sizes(self) -> None:
        while not self._stop.is_set():
            interval = max(60, int(settings.get("size_poll_interval_seconds")))
            try:
                await asyncio.to_thread(self._collect_sizes_once)
                self.last_size_ok = db.now_ts()
            except Exception as e:
                self.last_error = f"sizes: {e}"
                log.exception("size collection failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    def _collect_sizes_once(self) -> None:
        client = docker_client.get_client()
        containers = docker_client.list_running_containers(client)
        ts = db.now_ts()
        rows = []

        from concurrent.futures import ThreadPoolExecutor

        sem_count = min(_SIZE_CONCURRENCY, max(1, len(containers)))
        with ThreadPoolExecutor(max_workers=sem_count) as ex:
            inspect_futs = {ex.submit(docker_client.inspect_with_size, client, c["id"]): c for c in containers}
            for fut in inspect_futs:
                c = inspect_futs[fut]
                try:
                    insp = fut.result()
                except Exception as e:
                    log.warning("inspect fut failed %s: %s", c["name"], e)
                    insp = None
                if insp is None:
                    continue
                sizes = docker_client.get_size_from_inspect(insp)
                data_dir_total: Optional[int] = None
                mounts = docker_client.get_mount_sources(insp)
                if os.path.isdir(docker_client.CONTAINER_APP_DATA_ROOT):
                    total = 0
                    counted = False
                    for src in mounts:
                        local = docker_client.host_path_to_container_path(src)
                        if local and os.path.isdir(local):
                            total += docker_client.du_bytes(local)
                            counted = True
                    if counted:
                        data_dir_total = total
                rows.append((c, sizes, data_dir_total))

        with db.get_conn() as conn:
            for c, sizes, data_dir_total in rows:
                db.insert_size_sample(
                    conn,
                    ts=ts,
                    container_id=c["id"],
                    rw_bytes=sizes["rw"],
                    root_fs_bytes=sizes["root_fs"],
                    data_dir_bytes=data_dir_total,
                )

    # ---------------- prune loop ----------------

    async def _loop_prune(self) -> None:
        # Run once a day; first run after 1h to let DB warm up
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=3600)
            if self._stop.is_set():
                return
        except asyncio.TimeoutError:
            pass
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self._prune_once)
            except Exception:
                log.exception("prune failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=86400)
            except asyncio.TimeoutError:
                pass

    def _prune_once(self) -> None:
        days = max(1, int(settings.get("retention_days")))
        cutoff = db.now_ts() - days * 86400
        with db.get_conn() as conn:
            deleted = db.prune_older_than(conn, cutoff)
        log.info("pruned %d rows older than %d days", deleted, days)


collector = Collector()

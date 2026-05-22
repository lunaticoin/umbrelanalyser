import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Iterator, Optional

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "umbrelanalyser.db")

_init_lock = threading.Lock()
_initialized = False


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    init_db()
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    global _initialized
    if _initialized:
        return
    with _init_lock:
        if _initialized:
            return
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    container_id TEXT NOT NULL,
                    cpu_percent REAL,
                    mem_bytes INTEGER,
                    mem_limit_bytes INTEGER,
                    mem_percent REAL,
                    blk_read_bytes INTEGER,
                    blk_write_bytes INTEGER,
                    net_rx_bytes INTEGER,
                    net_tx_bytes INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts);
                CREATE INDEX IF NOT EXISTS idx_samples_cid_ts ON samples(container_id, ts);

                CREATE TABLE IF NOT EXISTS size_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts INTEGER NOT NULL,
                    container_id TEXT NOT NULL,
                    rw_bytes INTEGER,
                    root_fs_bytes INTEGER,
                    data_dir_bytes INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_size_ts ON size_samples(ts);
                CREATE INDEX IF NOT EXISTS idx_size_cid_ts ON size_samples(container_id, ts);

                CREATE TABLE IF NOT EXISTS containers (
                    container_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    image TEXT,
                    first_seen INTEGER NOT NULL,
                    last_seen INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
        finally:
            conn.close()
        _initialized = True


def upsert_container(conn: sqlite3.Connection, container_id: str, name: str, image: str, now: int) -> None:
    conn.execute(
        """
        INSERT INTO containers (container_id, name, image, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(container_id) DO UPDATE SET
            name=excluded.name,
            image=excluded.image,
            last_seen=excluded.last_seen
        """,
        (container_id, name, image, now, now),
    )


def insert_sample(
    conn: sqlite3.Connection,
    ts: int,
    container_id: str,
    cpu_percent: Optional[float],
    mem_bytes: Optional[int],
    mem_limit_bytes: Optional[int],
    mem_percent: Optional[float],
    blk_read_bytes: Optional[int],
    blk_write_bytes: Optional[int],
    net_rx_bytes: Optional[int],
    net_tx_bytes: Optional[int],
) -> None:
    conn.execute(
        """
        INSERT INTO samples
            (ts, container_id, cpu_percent, mem_bytes, mem_limit_bytes, mem_percent,
             blk_read_bytes, blk_write_bytes, net_rx_bytes, net_tx_bytes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (ts, container_id, cpu_percent, mem_bytes, mem_limit_bytes, mem_percent,
         blk_read_bytes, blk_write_bytes, net_rx_bytes, net_tx_bytes),
    )


def insert_size_sample(
    conn: sqlite3.Connection,
    ts: int,
    container_id: str,
    rw_bytes: Optional[int],
    root_fs_bytes: Optional[int],
    data_dir_bytes: Optional[int],
) -> None:
    conn.execute(
        """
        INSERT INTO size_samples (ts, container_id, rw_bytes, root_fs_bytes, data_dir_bytes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (ts, container_id, rw_bytes, root_fs_bytes, data_dir_bytes),
    )


def prune_older_than(conn: sqlite3.Connection, ts_cutoff: int) -> int:
    cur = conn.execute("DELETE FROM samples WHERE ts < ?", (ts_cutoff,))
    deleted_a = cur.rowcount or 0
    cur = conn.execute("DELETE FROM size_samples WHERE ts < ?", (ts_cutoff,))
    deleted_b = cur.rowcount or 0
    conn.execute("VACUUM")
    return deleted_a + deleted_b


def list_containers(conn: sqlite3.Connection):
    return conn.execute(
        "SELECT container_id, name, image, first_seen, last_seen FROM containers ORDER BY name COLLATE NOCASE"
    ).fetchall()


def latest_sample(conn: sqlite3.Connection, container_id: str):
    return conn.execute(
        "SELECT * FROM samples WHERE container_id = ? ORDER BY ts DESC LIMIT 1",
        (container_id,),
    ).fetchone()


def latest_size_sample(conn: sqlite3.Connection, container_id: str):
    return conn.execute(
        "SELECT * FROM size_samples WHERE container_id = ? ORDER BY ts DESC LIMIT 1",
        (container_id,),
    ).fetchone()


def samples_range(conn: sqlite3.Connection, container_id: str, ts_from: int, ts_to: int):
    return conn.execute(
        """
        SELECT ts, cpu_percent, mem_bytes, mem_limit_bytes, mem_percent,
               blk_read_bytes, blk_write_bytes, net_rx_bytes, net_tx_bytes
        FROM samples
        WHERE container_id = ? AND ts BETWEEN ? AND ?
        ORDER BY ts ASC
        """,
        (container_id, ts_from, ts_to),
    ).fetchall()


def size_samples_range(conn: sqlite3.Connection, container_id: str, ts_from: int, ts_to: int):
    return conn.execute(
        """
        SELECT ts, rw_bytes, root_fs_bytes, data_dir_bytes
        FROM size_samples
        WHERE container_id = ? AND ts BETWEEN ? AND ?
        ORDER BY ts ASC
        """,
        (container_id, ts_from, ts_to),
    ).fetchall()


def db_stats(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) AS n, MIN(ts) AS min_ts, MAX(ts) AS max_ts FROM samples"
    ).fetchone()
    size = 0
    try:
        size = os.path.getsize(DB_PATH)
    except OSError:
        pass
    return {
        "samples": row["n"] or 0,
        "oldest_ts": row["min_ts"],
        "newest_ts": row["max_ts"],
        "db_bytes": size,
    }


def now_ts() -> int:
    return int(time.time())

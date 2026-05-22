import csv
import io
import json
from typing import Iterable, Mapping


SAMPLE_FIELDS = [
    "ts", "cpu_percent", "mem_bytes", "mem_limit_bytes", "mem_percent",
    "blk_read_bytes", "blk_write_bytes", "net_rx_bytes", "net_tx_bytes",
]

SIZE_FIELDS = ["ts", "rw_bytes", "root_fs_bytes", "data_dir_bytes"]


def rows_to_csv(rows: Iterable[Mapping], fields: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r[k] for k in fields})
    return buf.getvalue()


def rows_to_json(
    container: Mapping,
    samples: Iterable[Mapping],
    size_samples: Iterable[Mapping],
    ts_from: int,
    ts_to: int,
) -> str:
    payload = {
        "container": {
            "id": container["container_id"],
            "name": container["name"],
            "image": container["image"],
        },
        "range": {"from": ts_from, "to": ts_to},
        "samples": [{k: r[k] for k in SAMPLE_FIELDS} for r in samples],
        "size_samples": [{k: r[k] for k in SIZE_FIELDS} for r in size_samples],
    }
    return json.dumps(payload, separators=(",", ":"), default=str)

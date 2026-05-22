import logging
import os
from typing import Any, Dict, List, Optional

import docker
from docker.errors import APIError, NotFound

log = logging.getLogger(__name__)

HOST_APP_DATA_ROOT = os.environ.get("HOST_APP_DATA_ROOT", "/home/umbrel/umbrel/app-data")
CONTAINER_APP_DATA_ROOT = os.environ.get("CONTAINER_APP_DATA_ROOT", "/host-app-data")


def get_client() -> docker.DockerClient:
    return docker.from_env()


def list_running_containers(client: docker.DockerClient) -> List[Dict[str, Any]]:
    out = []
    for c in client.containers.list(all=False):
        image = ""
        try:
            tags = c.image.tags
            image = tags[0] if tags else (c.image.id or "")
        except Exception:
            pass
        out.append({"id": c.id, "name": c.name, "image": image, "obj": c})
    return out


def get_stats(client: docker.DockerClient, container_id: str) -> Optional[Dict[str, Any]]:
    try:
        return client.api.stats(container_id, stream=False)
    except (NotFound, APIError) as e:
        log.warning("stats failed for %s: %s", container_id[:12], e)
        return None


def inspect_with_size(client: docker.DockerClient, container_id: str) -> Optional[Dict[str, Any]]:
    try:
        return client.api.inspect_container(container_id, size=True)
    except (NotFound, APIError) as e:
        log.warning("inspect failed for %s: %s", container_id[:12], e)
        return None


def get_mount_sources(inspect: Dict[str, Any]) -> List[str]:
    return [m.get("Source", "") for m in inspect.get("Mounts", []) if m.get("Source")]


def host_path_to_container_path(host_path: str) -> Optional[str]:
    """Rewrite a host bind-mount path into the path we can read from inside our container.

    Only works for paths under HOST_APP_DATA_ROOT mounted at CONTAINER_APP_DATA_ROOT.
    Returns None if the path is outside our visibility.
    """
    if not host_path.startswith(HOST_APP_DATA_ROOT.rstrip("/") + "/") and host_path != HOST_APP_DATA_ROOT:
        return None
    relative = host_path[len(HOST_APP_DATA_ROOT):].lstrip("/")
    return os.path.join(CONTAINER_APP_DATA_ROOT, relative) if relative else CONTAINER_APP_DATA_ROOT


def du_bytes(path: str) -> int:
    total = 0
    for root, _dirs, files in os.walk(path, followlinks=False):
        for f in files:
            fp = os.path.join(root, f)
            try:
                st = os.lstat(fp)
                total += st.st_size
            except OSError:
                pass
    return total


# ------------------ stats parsing ------------------

def parse_cpu_percent(cur: Dict[str, Any], prev: Optional[Dict[str, Any]]) -> Optional[float]:
    """Compute CPU% from delta between two snapshots. Returns None if not computable."""
    try:
        cur_cpu = cur["cpu_stats"]
        prev_cpu = prev["cpu_stats"] if prev else None
        cur_total = cur_cpu["cpu_usage"]["total_usage"]
        cur_sys = cur_cpu.get("system_cpu_usage")
        if cur_sys is None or prev_cpu is None:
            return None
        prev_total = prev_cpu["cpu_usage"]["total_usage"]
        prev_sys = prev_cpu.get("system_cpu_usage")
        if prev_sys is None:
            return None
        cpu_delta = cur_total - prev_total
        sys_delta = cur_sys - prev_sys
        if sys_delta <= 0 or cpu_delta < 0:
            return None
        online = cur_cpu.get("online_cpus") or len(cur_cpu["cpu_usage"].get("percpu_usage") or []) or 1
        return round((cpu_delta / sys_delta) * online * 100.0, 4)
    except (KeyError, TypeError, ZeroDivisionError):
        return None


def parse_mem(cur: Dict[str, Any]) -> Dict[str, Optional[float]]:
    try:
        mem = cur["memory_stats"]
        usage = mem.get("usage")
        # docker stats includes cache in usage; subtract if available (matches `docker stats` CLI)
        stats = mem.get("stats") or {}
        cache = stats.get("inactive_file") or stats.get("cache") or 0
        if usage is not None and cache and cache <= usage:
            used = usage - cache
        else:
            used = usage
        limit = mem.get("limit")
        pct = round((used / limit) * 100.0, 4) if used is not None and limit else None
        return {"bytes": used, "limit": limit, "percent": pct}
    except (KeyError, TypeError, ZeroDivisionError):
        return {"bytes": None, "limit": None, "percent": None}


def parse_blkio(cur: Dict[str, Any]) -> Dict[str, Optional[int]]:
    """Cumulative read/write bytes across all devices."""
    read_b = 0
    write_b = 0
    found = False
    try:
        entries = (cur.get("blkio_stats") or {}).get("io_service_bytes_recursive") or []
        for e in entries:
            op = (e.get("op") or "").lower()
            val = e.get("value") or 0
            if op == "read":
                read_b += val
                found = True
            elif op == "write":
                write_b += val
                found = True
    except (TypeError, AttributeError):
        pass
    if not found:
        return {"read": None, "write": None}
    return {"read": read_b, "write": write_b}


def parse_net(cur: Dict[str, Any]) -> Dict[str, Optional[int]]:
    nets = cur.get("networks") or {}
    if not nets:
        return {"rx": None, "tx": None}
    rx = 0
    tx = 0
    for _name, iface in nets.items():
        rx += iface.get("rx_bytes") or 0
        tx += iface.get("tx_bytes") or 0
    return {"rx": rx, "tx": tx}


def get_size_from_inspect(inspect: Dict[str, Any]) -> Dict[str, Optional[int]]:
    return {
        "rw": inspect.get("SizeRw"),
        "root_fs": inspect.get("SizeRootFs"),
    }

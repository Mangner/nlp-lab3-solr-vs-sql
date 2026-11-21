"""Zbiera informacje o sprzęcie i wersjach (wymagane w sprawozdaniu) -> results/environment.json.

Uruchomienie:  python -m lab3.environment
"""
import json
import platform
import shutil
import subprocess
import sys

import psutil

from lab3.config import config
from lab3.db import pg_connect
from lab3.measure import now, save_json
from lab3.solr import solr_get


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except Exception:
        return ""


def cpu_name() -> str:
    system = platform.system()
    if system == "Windows":
        out = run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"])
        return out.splitlines()[0].strip() if out else platform.processor()
    if system == "Darwin":
        return run(["sysctl", "-n", "machdep.cpu.brand_string"]) or platform.processor()
    try:
        for line in open("/proc/cpuinfo", encoding="utf-8"):
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor()


def disk_info() -> dict:
    d = shutil.disk_usage(config.data_dir if config.data_dir.exists() else ".")
    info = {"total_gb": round(d.total / 2**30), "free_gb": round(d.free / 2**30)}
    if platform.system() == "Windows":
        out = run(["powershell", "-NoProfile", "-Command",
                   "Get-PhysicalDisk | Select-Object FriendlyName,MediaType,Size | ConvertTo-Json -Compress"])
        if out:
            try:
                info["physical_disks"] = json.loads(out)
            except json.JSONDecodeError:
                pass
    return info


def main() -> int:
    env = {
        "timestamp": now(),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "cpu": cpu_name(),
        "cpu_cores_physical": psutil.cpu_count(logical=False),
        "cpu_threads": psutil.cpu_count(logical=True),
        "ram_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "disk": disk_info(),
        "python": sys.version.split()[0],
        "docker_version": run(["docker", "version", "--format", "{{.Server.Version}}"]),
        "docker_resources": run(["docker", "info", "--format", "{{.NCPU}} CPU, {{.MemTotal}} B RAM"]),
    }
    try:
        info = solr_get("admin/info/system")
        env["solr"] = {"version": info["lucene"]["solr-spec-version"], "lucene": info["lucene"]["lucene-spec-version"],
                       "mode": info.get("mode"), "jvm_max_heap_gb": round(info["jvm"]["memory"]["raw"]["max"] / 2**30, 2),
                       "jvm": f"{info['jvm'].get('name')} {info['jvm'].get('version')}"}
        envlines = run(["docker", "inspect", "lab3-solr", "--format", "{{range .Config.Env}}{{println .}}{{end}}"]).splitlines()
        env["solr"]["SOLR_HEAP"] = next((l.split("=", 1)[1] for l in envlines if l.startswith("SOLR_HEAP=")), None)
    except Exception as exc:
        env["solr"] = {"error": str(exc)}
    try:
        with pg_connect() as conn:
            env["postgres"] = {
                "version": conn.execute("SHOW server_version").fetchone()[0],
                "settings": {r[0]: r[1] for r in conn.execute(
                    "SELECT name, current_setting(name) FROM pg_settings WHERE name IN ('shared_buffers','work_mem','maintenance_work_mem',"
                    "'effective_cache_size','max_wal_size','checkpoint_timeout','max_parallel_workers_per_gather',"
                    "'max_parallel_workers','max_worker_processes','jit','default_text_search_config') ORDER BY 1")},
            }
    except Exception as exc:
        env["postgres"] = {"error": str(exc)}
    save_json(config.results_dir / "environment.json", env)
    print(json.dumps(env, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

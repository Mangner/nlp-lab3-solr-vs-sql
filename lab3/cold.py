"""Etap 6 (opcjonalnie): pomiar „zimnego startu” — pierwsze zapytanie po restarcie kontenerów.

Uruchomienie:  python -m lab3.cold [--size 100] [--drop-vm-cache]
Metoda: `docker compose restart postgres solr` (czyści shared_buffers Postgresa oraz pamięć JVM/cache'e Solra),
opcjonalnie (--drop-vm-cache) dodatkowo zrzut page cache maszyny wirtualnej Dockera
(`docker run --privileged alpine … drop_caches`); bez tej opcji cache plików systemu hosta/VM pozostaje ciepły,
więc wynik to „zimny proces”, a nie w pełni „zimny dysk”. Mierzymy PIERWSZE wykonanie każdego zapytania.
Wynik: results/cold.json
"""
import argparse
import subprocess
import sys
import time

import requests

from lab3.config import ROOT, config
from lab3.db import pg_connect
from lab3.measure import nocache, now, save_json, solr_run
from lab3.queries import QUERIES, count_sql, edismax_params, top_sql


def wait_ready(timeout: int = 180) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with pg_connect(connect_timeout=3) as c:
                c.execute("SELECT 1")
            if requests.get(f"{config.solr_url}/admin/info/system", timeout=3).ok:
                return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError("kontenery nie wstały")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="100")
    ap.add_argument("--drop-vm-cache", action="store_true")
    args = ap.parse_args()
    t = f"papers_{args.size}"
    subprocess.run(["docker", "compose", "restart", "postgres", "solr"], cwd=ROOT, check=True)
    wait_ready()
    dropped = False
    if args.drop_vm_cache:
        r = subprocess.run(["docker", "run", "--rm", "--privileged", "alpine", "sh", "-c",
                            "sync; echo 3 > /proc/sys/vm/drop_caches"], capture_output=True, text=True)
        dropped = r.returncode == 0
        print("drop_caches:", "OK" if dropped else f"nieudane ({r.stderr.strip()[:100]})")
    # Solr ładuje rdzenie po starcie — poczekaj aż kolekcja odpowiada
    for _ in range(60):
        try:
            solr_run(t, {"q": "id:none", "rows": 0})
            break
        except Exception:
            time.sleep(2)
    results = []
    with pg_connect(autocommit=True) as conn:
        for key, q in QUERIES.items():
            for method, fn in (
                ("FTS count", lambda: conn.execute(count_sql(t, f"tsv @@ {q.tsquery}")).fetchall()),
                ("FTS top10", lambda: conn.execute(top_sql(t, q)).fetchall()),
                ("Solr count", lambda: solr_run(t, nocache({"q": q.solr_q, "rows": 0}))),
                ("Solr top10", lambda: solr_run(t, nocache(edismax_params(q)))),
            ):
                t0 = time.perf_counter()
                fn()
                ms = (time.perf_counter() - t0) * 1000
                results.append({"query_key": key, "method": method, "first_run_client_ms": round(ms, 2), "timestamp": now()})
                print(f"{key} {method:10s} pierwsze wykonanie: {ms:9.1f} ms", flush=True)
    save_json(config.results_dir / "cold.json", {"timestamp": now(), "size": args.size, "vm_page_cache_dropped": dropped,
                                                 "method": "docker compose restart postgres solr", "results": results})
    return 0


if __name__ == "__main__":
    sys.exit(main())

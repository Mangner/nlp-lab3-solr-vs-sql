"""Wspólne narzędzia pomiarowe: PostgreSQL (EXPLAIN ANALYZE + czas klienta) i Solr (QTime + czas klienta).

Zasady (patrz CLAUDE.md): 1 rozgrzewka + N pomiarów, mediana (oraz min/max); zapisujemy dokładne zapytanie
(pełny SQL albo pełny URL Solra), liczbę wyników, czas i znacznik czasu.
"""
import datetime as dt
import json
import statistics
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from lab3.config import config

REPEATS = 5


def now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def summarize(values: list[float]) -> dict:
    return {"median": round(statistics.median(values), 3), "min": round(min(values), 3),
            "max": round(max(values), 3), "runs": [round(v, 3) for v in values]}


# ----------------------------------------------------------------------------------------------- PostgreSQL
def pg_measure(conn, sql: str, repeats: int = REPEATS, label: str = "", size: str = "", explain_text_to: Path | None = None) -> dict:
    """Mierzy zapytanie: czas klienta (wykonanie + pobranie wyników) i Execution Time z EXPLAIN (ANALYZE, BUFFERS).

    Pierwsze uruchomienie (rozgrzewka) jest pomijane. Zwraca też liczbę wierszy wyniku.
    """
    client, server = [], []
    nrows = None
    conn.execute(sql).fetchall()  # rozgrzewka
    for _ in range(repeats):
        t0 = time.perf_counter()
        rows = conn.execute(sql).fetchall()
        client.append((time.perf_counter() - t0) * 1000)
        nrows = rows[0][0] if len(rows) == 1 and len(rows[0]) == 1 and isinstance(rows[0][0], int) else len(rows)
        plan = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql).fetchone()[0][0]
        server.append(plan["Execution Time"])
    if explain_text_to is not None:
        txt = "\n".join(r[0] for r in conn.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql).fetchall())
        explain_text_to.parent.mkdir(parents=True, exist_ok=True)
        explain_text_to.write_text(f"-- {label} ({size}%)\n{sql}\n\n{txt}\n", encoding="utf-8")
    return {"engine": "postgres", "label": label, "size": size, "query": sql, "result_count": nrows,
            "exec_ms": summarize(server), "client_ms": summarize(client), "timestamp": now()}


def pg_plan_flags(conn, sql: str) -> dict:
    """Skrót planu: czy użyto Parallel Seq Scan / Bitmap Index Scan na GIN (do opisu w sprawozdaniu)."""
    txt = "\n".join(r[0] for r in conn.execute("EXPLAIN " + sql).fetchall())
    return {"parallel_seq_scan": "Parallel Seq Scan" in txt, "seq_scan": "Seq Scan" in txt,
            "gin_bitmap": "Bitmap Index Scan" in txt, "plan": txt}


# ----------------------------------------------------------------------------------------------- Solr
def solr_url(collection: str, params: dict) -> str:
    """Pełny URL zapytania (z wt=json) — do wklejenia w przeglądarkę."""
    p = dict(params)
    p.setdefault("wt", "json")
    return f"{config.solr_url}/{collection}/select?{urlencode(p, doseq=True)}"


def solr_run(collection: str, params: dict) -> dict:
    url = solr_url(collection, params)
    t0 = time.perf_counter()
    r = requests.get(url, timeout=120)
    client_ms = (time.perf_counter() - t0) * 1000
    r.raise_for_status()
    js = r.json()
    return {"url": url, "qtime": js["responseHeader"]["QTime"], "client_ms": client_ms,
            "numFound": js["response"]["numFound"], "docs": js["response"]["docs"], "json": js}


def solr_measure(collection: str, params: dict, repeats: int = REPEATS, label: str = "", size: str = "") -> dict:
    solr_run(collection, params)  # rozgrzewka
    qt, cl = [], []
    last = None
    for _ in range(repeats):
        last = solr_run(collection, params)
        qt.append(float(last["qtime"]))
        cl.append(last["client_ms"])
    return {"engine": "solr", "label": label, "size": size, "query": last["url"], "result_count": last["numFound"],
            "qtime_ms": summarize(qt), "client_ms": summarize(cl), "timestamp": now()}


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"Zapisano {path}")

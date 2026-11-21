"""Etap 3: ładowanie zbiorów do PostgreSQL (COPY) i budowa indeksów, z pomiarem czasów.

Uruchomienie:  python -m lab3.load_pg [--sizes 10 50 100] [--data-dir KATALOG] [--out PLIK.json]

Dla każdej tabeli papers_<N>: DROP/CREATE (sql/01_schema.sql) -> COPY z pliku CSV (strumieniowo, po stronie
klienta) -> CREATE INDEX GIN na tsv -> B-tree na year i primary_category -> ANALYZE (sql/02_indexes.sql).
Mierzymy osobno: COPY (zawiera obliczanie kolumny tsv), budowę GIN, B-tree, ANALYZE oraz rozmiary.
Skrypt jest idempotentny (tabela jest za każdym razem tworzona od nowa).
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

from tqdm import tqdm

from lab3.config import ROOT, config
from lab3.db import pg_connect

COLUMNS = "id, title, abstract, primary_category, archive, categories, year, license"
CHUNK = 4 * 1024 * 1024


def read_sections(path: Path) -> dict[str, str]:
    """Dzieli plik SQL na sekcje oznaczone komentarzem '-- @nazwa'."""
    sections, name, buf = {}, None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"--\s*@(\w+)\s*$", line)
        if m:
            if name:
                sections[name] = "\n".join(buf)
            name, buf = m.group(1), []
        elif name:
            buf.append(line)
    if name:
        sections[name] = "\n".join(buf)
    return sections


def timed(conn, sql: str) -> float:
    t0 = time.perf_counter()
    conn.execute(sql)
    return time.perf_counter() - t0


def load_table(conn, size: str, data_dir: Path, schema_sql: str, idx: dict[str, str]) -> dict:
    t = f"papers_{size}"
    csv_path = data_dir / f"{t}.csv"
    nbytes = csv_path.stat().st_size
    print(f"\n=== {t}: {csv_path} ({nbytes / 2**20:.0f} MiB) ===")
    conn.execute(schema_sql.replace("{t}", t))

    t0 = time.perf_counter()
    with conn.cursor() as cur, cur.copy(
        f"COPY {t} ({COLUMNS}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    ) as copy, open(csv_path, "rb") as f, tqdm(total=nbytes, unit="B", unit_scale=True, desc=f"COPY {t}") as bar:
        while chunk := f.read(CHUNK):
            copy.write(chunk)
            bar.update(len(chunk))
    copy_s = time.perf_counter() - t0
    rows = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    print(f"COPY: {copy_s:.1f} s, wierszy: {rows}")

    res = {"table": t, "rows": rows, "csv_bytes": nbytes, "copy_seconds": round(copy_s, 2)}
    res["gin_seconds"] = round(timed(conn, idx["gin"].replace("{t}", t)), 2)
    print(f"GIN: {res['gin_seconds']} s")
    res["btree_year_seconds"] = round(timed(conn, idx["btree_year"].replace("{t}", t)), 2)
    res["btree_category_seconds"] = round(timed(conn, idx["btree_category"].replace("{t}", t)), 2)
    res["analyze_seconds"] = round(timed(conn, idx["analyze"].replace("{t}", t)), 2)
    print(f"B-tree: {res['btree_year_seconds']} + {res['btree_category_seconds']} s, ANALYZE: {res['analyze_seconds']} s")

    q = conn.execute(
        """SELECT pg_relation_size(%(t)s), pg_table_size(%(t)s), pg_indexes_size(%(t)s), pg_total_relation_size(%(t)s),
                  pg_relation_size(%(g)s), pg_relation_size(%(y)s), pg_relation_size(%(c)s), pg_relation_size(%(p)s)""",
        {"t": t, "g": f"{t}_tsv_gin", "y": f"{t}_year_idx", "c": f"{t}_primary_category_idx", "p": f"{t}_pkey"},
    ).fetchone()
    res.update(dict(zip(
        ["heap_bytes", "table_bytes_with_toast", "indexes_bytes", "total_bytes",
         "gin_bytes", "btree_year_bytes", "btree_category_bytes", "pkey_bytes"], q)))
    res["avg_tsv_bytes"] = conn.execute(f"SELECT avg(pg_column_size(tsv))::int FROM {t}").fetchone()[0]
    print(f"rozmiary [MiB]: tabela(z TOAST) {res['table_bytes_with_toast'] / 2**20:.0f}, "
          f"GIN {res['gin_bytes'] / 2**20:.0f}, wszystkie indeksy {res['indexes_bytes'] / 2**20:.0f}")
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", nargs="+", default=["10", "50", "100"], choices=["10", "50", "100"])
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    data_dir = Path(args.data_dir) if args.data_dir else config.data_dir
    out = Path(args.out) if args.out else config.results_dir / "load_pg.json"

    schema_sql = (ROOT / "sql" / "01_schema.sql").read_text(encoding="utf-8")
    idx = read_sections(ROOT / "sql" / "02_indexes.sql")
    results = []
    with pg_connect(autocommit=True) as conn:
        for size in args.sizes:
            results.append(load_table(conn, size, data_dir, schema_sql, idx))
        settings = {
            r[0]: r[1] for r in conn.execute(
                "SELECT name, setting || coalesce(unit, '') FROM pg_settings WHERE name IN "
                "('shared_buffers','work_mem','maintenance_work_mem','effective_cache_size','max_wal_size',"
                "'max_parallel_workers_per_gather','max_parallel_maintenance_workers','default_text_search_config')")
        }
        version = conn.execute("SHOW server_version").fetchone()[0]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "postgres_version": version, "settings": settings, "tables": results,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nZapisano {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

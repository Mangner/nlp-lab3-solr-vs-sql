"""Etap 7b (poziom 5.0, rozszerzenie 1): głębokie stronicowanie — Solr start/rows vs cursorMark, SQL OFFSET/LIMIT.

Uruchomienie:  python -m lab3.paging [--size 100] [--rows 1000] [--repeats 3]
Zapytanie szerokie: (model OR method) — ok. 5·10^5 trafień w 100%. Sortowanie: score desc, id asc (Solr) oraz
ts_rank_cd DESC, id ASC (SQL) — porządek całkowity, więc cursorMark jest poprawny.
Dla każdej głębokości D mierzymy pobranie strony `rows` dokumentów zaczynającej się od pozycji D:
  * start/rows:   start=D&rows=R (kolejka priorytetowa rozmiaru D+R po stronie serwera),
  * cursorMark:   żądanie z kursorem otrzymanym po przejściu do pozycji D (kursor jest bezstanowy, więc to samo
                  żądanie można powtórzyć); osobno zapisujemy koszt dojścia do D (suma żądań kolejnych stron),
  * SQL OFFSET:   ORDER BY rank DESC, id LIMIT R OFFSET D.
Wynik: results/paging.json
"""
import argparse
import sys
import time

from lab3.config import config
from lab3.db import pg_connect
from lab3.measure import now, save_json, solr_run, summarize

SOLR_Q = "text_all:(model OR method)"
PG_TSQ = "to_tsquery('english', 'model | method')"
DEPTHS = [0, 1_000, 10_000, 100_000, 250_000, 500_000]


def params(rows: int, **extra) -> dict:
    p = {"q": SOLR_Q, "fl": "id", "sort": "score desc, id asc", "rows": rows}
    p.update(extra)
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="100", choices=["10", "50", "100"])
    ap.add_argument("--rows", type=int, default=1000)
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()
    t, R = f"papers_{args.size}", args.rows
    total = solr_run(t, params(0))["numFound"]
    depths = [d for d in DEPTHS if d + R <= total]
    print(f"Zbiór {t}: numFound={total}, głębokości: {depths}, rows={R}")

    # --- cursorMark: przejście przez wszystkie strony, zapamiętanie kursora dla każdej głębokości ---
    cursors = {}
    cur = "*"
    pos = 0
    walk_time = 0.0
    walk_times = {}
    ids_cursor = {}
    while pos <= max(depths):
        if pos in depths:
            cursors[pos] = cur
        t0 = time.perf_counter()
        r = solr_run(t, params(R, cursorMark=cur))
        walk_time += time.perf_counter() - t0
        if pos in depths:
            ids_cursor[pos] = [d["id"] for d in r["docs"]]
        pos += R
        walk_times[pos] = round(walk_time, 3)
        cur = r["json"]["nextCursorMark"]
    results = []
    with pg_connect(autocommit=True) as conn:
        for D in depths:
            entry = {"depth": D, "rows": R}
            # start/rows
            p = params(R, start=D)
            solr_run(t, p)
            runs = [solr_run(t, p) for _ in range(args.repeats)]
            entry["solr_start_rows"] = {"url": runs[-1]["url"], "client_ms": summarize([x["client_ms"] for x in runs]),
                                        "qtime_ms": summarize([float(x["qtime"]) for x in runs])}
            ids_sr = [d["id"] for d in runs[-1]["docs"]]
            # cursorMark (to samo żądanie z kursorem dla głębokości D)
            p = params(R, cursorMark=cursors[D])
            solr_run(t, p)
            runs = [solr_run(t, p) for _ in range(args.repeats)]
            entry["solr_cursor"] = {"url": runs[-1]["url"], "client_ms": summarize([x["client_ms"] for x in runs]),
                                    "qtime_ms": summarize([float(x["qtime"]) for x in runs]),
                                    "cumulative_walk_seconds_to_reach": walk_times.get(D, 0.0)}
            entry["same_page_start_vs_cursor"] = ids_sr == ids_cursor[D]
            # SQL OFFSET
            sql = (f"SELECT id FROM {t}, (SELECT {PG_TSQ} AS q) s WHERE tsv @@ s.q "
                   f"ORDER BY ts_rank_cd(tsv, s.q) DESC, id ASC LIMIT {R} OFFSET {D}")
            conn.execute(sql).fetchall()
            ts, ex = [], []
            for _ in range(args.repeats):
                t0 = time.perf_counter()
                conn.execute(sql).fetchall()
                ts.append((time.perf_counter() - t0) * 1000)
            ex.append(conn.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql).fetchone()[0][0]["Execution Time"])
            entry["sql_offset"] = {"sql": sql, "client_ms": summarize(ts), "exec_ms": round(ex[0], 3)}
            results.append(entry)
            print(f"D={D:>7}: start/rows {entry['solr_start_rows']['client_ms']['median']:>9.1f} ms | cursor "
                  f"{entry['solr_cursor']['client_ms']['median']:>7.1f} ms | SQL OFFSET {entry['sql_offset']['client_ms']['median']:>9.1f} ms "
                  f"| ta sama strona: {entry['same_page_start_vs_cursor']}", flush=True)
    save_json(config.results_dir / "paging.json", {
        "timestamp": now(), "size": args.size, "solr_q": SOLR_Q, "pg_tsquery": PG_TSQ, "numFound": total,
        "rows": R, "repeats": args.repeats, "results": results})
    return 0


if __name__ == "__main__":
    sys.exit(main())

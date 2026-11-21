"""Etapy 6–7: benchmark Q1–Q3 × (LIKE, FTS SQL, Solr) × rozmiary zbioru (10 / 50 / 100%).

Uruchomienie:  python -m lab3.bench [--sizes 10 50 100] [--repeats 5]
Tryby:
  count — liczba trafień: SELECT count(*) (LIKE i FTS) vs Solr q=…&rows=0 (czysty koszt dopasowania),
        Solr mierzony w dwóch wariantach: `Solr` = cache=false (realne wykonanie), `Solr+cache` = domyślnie (queryResultCache),
  top10 — top-10 wg trafności: ts_rank_cd ORDER BY … LIMIT 10 vs Solr eDisMax (LIKE nie ma rankingu).
Każdy pomiar: 1 rozgrzewka + N powtórzeń, mediana/min/max; zapis dokładnego SQL / URL. Wynik: results/benchmark.json
"""
import argparse
import sys

from lab3.config import config
from lab3.db import pg_connect
from lab3.measure import nocache, now, pg_measure, save_json, solr_measure
from lab3.queries import QUERIES, count_sql, edismax_params, top_sql


def run(sizes: list[str], repeats: int) -> list[dict]:
    out = []
    with pg_connect(autocommit=True) as conn:
        for size in sizes:
            t = f"papers_{size}"
            for key, q in QUERIES.items():
                jobs = [
                    ("count", "LIKE", lambda: pg_measure(conn, count_sql(t, q.like_where), repeats, f"{key} LIKE count", size)),
                    ("count", "FTS", lambda: pg_measure(conn, count_sql(t, f"tsv @@ {q.tsquery}"), repeats, f"{key} FTS count", size)),
                    ("count", "Solr", lambda: solr_measure(t, nocache({"q": q.solr_q, "rows": 0}), repeats, f"{key} Solr count (cache=false)", size)),
                    ("count", "Solr+cache", lambda: solr_measure(t, {"q": q.solr_q, "rows": 0}, repeats, f"{key} Solr count (queryResultCache)", size)),
                    ("top10", "FTS", lambda: pg_measure(conn, top_sql(t, q), repeats, f"{key} FTS top10", size)),
                    ("top10", "Solr", lambda: solr_measure(t, nocache(edismax_params(q)), repeats, f"{key} Solr top10 (cache=false)", size)),
                    ("top10", "Solr+cache", lambda: solr_measure(t, edismax_params(q), repeats, f"{key} Solr top10 (queryResultCache)", size)),
                ]
                for mode, method, fn in jobs:
                    m = fn()
                    m.update({"query_key": key, "mode": mode, "method": method})
                    out.append(m)
                    ms = m["exec_ms"]["median"] if "exec_ms" in m else m["qtime_ms"]["median"]
                    print(f"[{size}%] {key} {mode:5s} {method:4s} wyniki={m['result_count']:>7} "
                          f"serwer={ms:>9.2f} ms  klient={m['client_ms']['median']:>9.2f} ms", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", nargs="+", default=["10", "50", "100"], choices=["10", "50", "100"])
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    results = run(args.sizes, args.repeats)
    save_json(config.results_dir / (args.out or "benchmark.json"),
              {"timestamp": now(), "repeats": args.repeats, "sizes": args.sizes, "measurements": results})
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Etap 5 (poziom 3.0): zapytania Q1–Q3 w LIKE / FTS PostgreSQL / Solr, tabela wyników, różnice w trafieniach.

Uruchomienie:  python -m lab3.level3 [--size 100]
Wyniki: results/level3.json, results/level3_table.md, results/level3_diffs.json, docs/zapytania_solr.md,
        results/explain/level3_*.txt (plany EXPLAIN (ANALYZE, BUFFERS)).
"""
import argparse
import sys

from lab3.config import ROOT, config
from lab3.db import pg_connect
from lab3.measure import now, pg_measure, pg_plan_flags, save_json, solr_measure, solr_run
from lab3.queries import FILTER_SOLR_FQ, FILTER_SQL, QUERIES, TOP_FL


def solr_params(q: str, fq: list[str] | None = None, rows: int = 10) -> dict:
    p = {"q": q, "fl": TOP_FL, "sort": "score desc, id asc", "rows": rows}
    if fq:
        p["fq"] = fq
    return p


def solr_all_ids(coll: str, params: dict) -> list[str]:
    """Wszystkie id wyniku (cursorMark) — do porównania zbiorów wyników SQL vs Solr."""
    p = {"q": params["q"], "fl": "id", "sort": "id asc", "rows": 20000, "cursorMark": "*"}
    if "fq" in params:
        p["fq"] = params["fq"]
    ids = []
    while True:
        r = solr_run(coll, p)
        ids += [d["id"] for d in r["docs"]]
        nxt = r["json"]["nextCursorMark"]
        if nxt == p["cursorMark"]:
            return ids
        p["cursorMark"] = nxt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", default="100", choices=["10", "50", "100"])
    ap.add_argument("--repeats", type=int, default=5)
    args = ap.parse_args()
    t = f"papers_{args.size}"
    res_dir = config.results_dir
    rows = []
    sets = {}
    with pg_connect(autocommit=True) as conn:
        specs = []
        for k, q in QUERIES.items():
            specs.append((k, q.title, f"WHERE {q.like_where}", f"WHERE tsv @@ {q.tsquery}", solr_params(q.solr_q), q.like_where, q.tsquery))
        q1 = QUERIES["Q1"]
        specs.append(("Q1+fq", "Q1 z filtrem: archive=astro-ph, lata 2010–2020", f"WHERE {q1.like_where} AND {FILTER_SQL}",
                      f"WHERE tsv @@ {q1.tsquery} AND {FILTER_SQL}", solr_params(q1.solr_q, FILTER_SOLR_FQ), None, None))
        for key, title, like_w, fts_w, sp, _, _ in specs:
            like_sql = f"SELECT count(*) FROM {t} {like_w}"
            fts_sql = f"SELECT count(*) FROM {t} {fts_w}"
            m_like = pg_measure(conn, like_sql, args.repeats, f"{key} LIKE", args.size, res_dir / "explain" / f"level3_{key}_like.txt")
            m_fts = pg_measure(conn, fts_sql, args.repeats, f"{key} FTS", args.size, res_dir / "explain" / f"level3_{key}_fts.txt")
            m_fts["plan_flags"] = {k: v for k, v in pg_plan_flags(conn, fts_sql).items() if k != "plan"}
            m_like["plan_flags"] = {k: v for k, v in pg_plan_flags(conn, like_sql).items() if k != "plan"}
            m_solr = solr_measure(t, sp, args.repeats, f"{key} Solr", args.size)
            rows.append({"key": key, "title": title, "like": m_like, "fts": m_fts, "solr": m_solr})
            print(f"{key}: LIKE={m_like['result_count']} ({m_like['exec_ms']['median']} ms)  FTS={m_fts['result_count']} "
                  f"({m_fts['exec_ms']['median']} ms)  Solr={m_solr['result_count']} (QTime {m_solr['qtime_ms']['median']} ms)")
            if key in QUERIES:
                sets[key] = {
                    "like": {r[0] for r in conn.execute(f"SELECT id FROM {t} {like_w}")},
                    "fts": {r[0] for r in conn.execute(f"SELECT id FROM {t} {fts_w}")},
                    "solr": set(solr_all_ids(t, sp)),
                }

        # --- różnice zbiorów wyników ---
        diffs = {}
        for key, s in sets.items():
            d = {"counts": {n: len(v) for n, v in s.items()},
                 "fts_and_solr": len(s["fts"] & s["solr"]), "fts_only": len(s["fts"] - s["solr"]),
                 "solr_only": len(s["solr"] - s["fts"]), "like_only_vs_fts": len(s["like"] - s["fts"]),
                 "fts_only_vs_like": len(s["fts"] - s["like"]), "like_and_fts": len(s["like"] & s["fts"])}
            ex = {}
            for name, ids in (("fts_only", sorted(s["fts"] - s["solr"])[:3]), ("solr_only", sorted(s["solr"] - s["fts"])[:3]),
                              ("like_only", sorted(s["like"] - s["fts"])[:3]), ("fts_not_like", sorted(s["fts"] - s["like"])[:3])):
                ex[name] = [
                    {"id": r[0], "title": r[1], "abstract": r[2]}
                    for r in conn.execute(f"SELECT id, title, abstract FROM {t} WHERE id = ANY(%s) ORDER BY id", (ids,))
                ]
            d["examples"] = ex
            diffs[key] = d
        save_json(res_dir / "level3_diffs.json", {"size": args.size, "timestamp": now(), "diffs": diffs})

    save_json(res_dir / "level3.json", {"size": args.size, "table": t, "timestamp": now(), "rows": rows})

    # --- tabela markdown ---
    lines = [f"Zbiór: tabela/kolekcja `{t}`. Czasy: mediana z {args.repeats} uruchomień po rozgrzewce.", "",
             "| zapytanie | wyniki LIKE | wyniki FTS (SQL) | numFound Solr | LIKE exec [ms] | FTS exec [ms] | FTS klient [ms] | Solr QTime [ms] | Solr klient [ms] |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['key']}: {r['title']} | {r['like']['result_count']} | {r['fts']['result_count']} | {r['solr']['result_count']} | "
                     f"{r['like']['exec_ms']['median']} | {r['fts']['exec_ms']['median']} | {r['fts']['client_ms']['median']} | "
                     f"{r['solr']['qtime_ms']['median']} | {r['solr']['client_ms']['median']} |")
    (res_dir / "level3_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # --- docs/zapytania_solr.md ---
    md = ["# Zapytania Solra (poziom 3.0) — URL-e do wklejenia w przeglądarkę", "",
          f"Kolekcja: `{t}`. Admin UI → Query: wklej `q`, `fq`, `fl`, `sort`, `rows`. Ten plik jest generowany przez `python -m lab3.level3`.", ""]
    for r in rows:
        url = r["solr"]["query"]
        md += [f"## {r['key']} — {r['title']}", "", f"- numFound: **{r['solr']['result_count']}**, QTime (mediana): {r['solr']['qtime_ms']['median']} ms",
               f"- [{url}]({url.replace(' ', '%20')})", ""]
    (ROOT / "docs" / "zapytania_solr.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())

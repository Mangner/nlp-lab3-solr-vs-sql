"""Etap 7c (poziom 5.0, rozszerzenie 2): aktualizacja danych — zmiany w PostgreSQL przenoszone do Solra.

Uruchomienie:
  python -m lab3.sync demo      # pełny scenariusz: zmiana + usunięcie rekordów -> sync -> weryfikacja -> przywrócenie
  python -m lab3.sync sync      # tylko synchronizacja (zmiany od ostatniego sync)
  python -m lab3.sync revert    # przywróć rekordy demo do stanu z pliku data/papers_100.jsonl i zsynchronizuj

Mechanizm: trigger BEFORE UPDATE ustawia updated_at, trigger AFTER DELETE zapisuje id do papers_100_deleted
(sql/03_sync.sql). Skrypt synchronizujący: SELECT … WHERE updated_at > last_sync -> /update (dokument nadpisuje stary
o tym samym id), usunięcia -> /update {"delete": …}; jeden commit; następnie zapis last_sync w tabeli sync_state.
Zakres demo (deterministyczny): pierwsze 13 rekordów z pliku papers_100.jsonl.
Log: results/sync_log.json (+ wypisywany na ekran).
"""
import argparse
import json
import sys

from lab3.config import ROOT, config
from lab3.db import pg_connect
from lab3.load_pg import read_sections
from lab3.measure import now, save_json, solr_run
from lab3.solr import solr_get
from lab3.load_solr import api

TABLE = "papers_100"
MARKER = "xqzmarkerupdate"
TITLE_MARKER = "xqztitlemarker"
LOG: list[dict] = []


def log(event: str, **data) -> None:
    entry = {"time": now(), "event": event, **data}
    LOG.append(entry)
    print(f"[{entry['time']}] {event} " + " ".join(f"{k}={v}" for k, v in data.items() if k != "detail"), flush=True)


def demo_records() -> list[dict]:
    with open(config.data_dir / f"{TABLE}.jsonl", encoding="utf-8") as f:
        return [json.loads(next(f)) for _ in range(13)]


def setup(conn) -> None:
    sec = read_sections(ROOT / "sql" / "03_sync.sql")
    conn.execute(sec["setup"].replace("{t}", TABLE))
    if conn.execute("SELECT 1 FROM sync_state WHERE tbl=%s", (TABLE,)).fetchone() is None:
        # po ładowaniu Solr jest zgodny z PG -> punkt startowy synchronizacji = teraz
        conn.execute("INSERT INTO sync_state VALUES (%s, clock_timestamp())", (TABLE,))
    log("setup", detail="triggery + tabele śledzące gotowe")


def to_doc(row) -> dict:
    keys = ["id", "title", "abstract", "primary_category", "archive", "categories", "year", "license"]
    return dict(zip(keys, row))


def sync(conn) -> dict:
    last = conn.execute("SELECT last_sync FROM sync_state WHERE tbl=%s", (TABLE,)).fetchone()[0]
    upper = conn.execute("SELECT clock_timestamp()").fetchone()[0]
    changed = conn.execute(
        f"SELECT id, title, abstract, primary_category, archive, categories, year, license FROM {TABLE} "
        "WHERE updated_at > %s AND updated_at <= %s ORDER BY id", (last, upper)).fetchall()
    deleted = [r[0] for r in conn.execute(
        f"SELECT DISTINCT id FROM {TABLE}_deleted WHERE deleted_at > %s AND deleted_at <= %s ORDER BY id", (last, upper))]
    # id usunięte i ponownie dodane (revert) nie mogą zostać usunięte w Solrze
    present = {r[0] for r in conn.execute(f"SELECT id FROM {TABLE} WHERE id = ANY(%s)", (deleted,))} if deleted else set()
    deleted = [i for i in deleted if i not in present]
    if changed:
        r = api("POST", f"{TABLE}/update?commit=false", json=[to_doc(r) for r in changed])
        assert r["responseHeader"]["status"] == 0
    if deleted:
        r = api("POST", f"{TABLE}/update?commit=false", json={"delete": [{"id": i} for i in deleted]})
        assert r["responseHeader"]["status"] == 0
    if changed or deleted:
        api("GET", f"{TABLE}/update", params={"commit": "true", "wt": "json"})
    conn.execute("UPDATE sync_state SET last_sync=%s WHERE tbl=%s", (upper, TABLE))
    log("sync", upserted=len(changed), deleted=len(deleted), upserted_ids=[r[0] for r in changed], deleted_ids=deleted)
    return {"upserted": [r[0] for r in changed], "deleted": deleted}


def solr_ids(q: str) -> set[str]:
    return {d["id"] for d in solr_get(f"{TABLE}/select", q=q, fl="id", rows=1000)["response"]["docs"]}


def verify(conn, changed_ids: list[str], deleted_ids: list[str], label: str) -> dict:
    checks = {}
    pg_n = conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
    sr_n = solr_get(f"{TABLE}/select", q="*:*", rows=0)["response"]["numFound"]
    checks["total_count"] = {"pg": pg_n, "solr": sr_n, "equal": pg_n == sr_n}
    # zapytania po słowie-znaczniku (identyczne id w obu systemach)
    for name, tsq, sq in (("marker_abstract", MARKER, f"text_all:{MARKER}"), ("marker_title", TITLE_MARKER, f"title:{TITLE_MARKER}")):
        pg_ids = {r[0] for r in conn.execute(f"SELECT id FROM {TABLE} WHERE tsv @@ to_tsquery('english', %s)", (tsq,))}
        sr_ids = solr_ids(sq)
        checks[name] = {"pg_ids": sorted(pg_ids), "solr_ids": sorted(sr_ids), "equal": pg_ids == sr_ids}
    # usunięte id nie istnieją w żadnym systemie
    if deleted_ids:
        pg_left = [r[0] for r in conn.execute(f"SELECT id FROM {TABLE} WHERE id = ANY(%s)", (deleted_ids,))]
        sr_left = list(solr_ids("id:(" + " OR ".join(f'"{i}"' for i in deleted_ids) + ")"))
        checks["deleted_absent"] = {"pg_left": pg_left, "solr_left": sr_left, "ok": not pg_left and not sr_left}
    # zmienione dokumenty: te same pola w PG i Solrze
    mism = []
    for i in changed_ids:
        pg = conn.execute(f"SELECT title, abstract FROM {TABLE} WHERE id=%s", (i,)).fetchone()
        docs = solr_get(f"{TABLE}/select", q=f'id:"{i}"', fl="title,abstract", rows=1)["response"]["docs"]
        if pg is None or not docs or (docs[0]["title"], docs[0]["abstract"]) != pg:
            mism.append(i)
    checks["changed_docs_identical"] = {"checked": len(changed_ids), "mismatches": mism, "ok": not mism}
    ok = all(v.get("equal", v.get("ok", False)) for v in checks.values())
    log(f"verify:{label}", ok=ok, **{k: (v.get("equal", v.get("ok"))) for k, v in checks.items()})
    LOG[-1]["detail"] = checks
    return {"ok": ok, "checks": checks}


def revert(conn) -> None:
    for rec in demo_records():
        conn.execute(
            f"INSERT INTO {TABLE} (id, title, abstract, primary_category, archive, categories, year, license) "
            "VALUES (%(id)s,%(title)s,%(abstract)s,%(primary_category)s,%(archive)s,%(categories)s,%(year)s,%(license)s) "
            "ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, abstract=EXCLUDED.abstract, "
            "primary_category=EXCLUDED.primary_category, archive=EXCLUDED.archive, categories=EXCLUDED.categories, "
            "year=EXCLUDED.year, license=EXCLUDED.license", rec)
    log("revert", detail="rekordy demo przywrócone do stanu z pliku JSONL")


def demo(conn) -> int:
    recs = demo_records()
    setup(conn)
    # stan wyjściowy: przywróć ewentualne pozostałości po poprzednim demo
    revert(conn)
    sync(conn)
    verify(conn, [r["id"] for r in recs], [], "baseline")

    upd_abs = [r["id"] for r in recs[0:5]]
    upd_title = [r["id"] for r in recs[5:8]]
    del_ids = [r["id"] for r in recs[8:13]]
    conn.execute(f"UPDATE {TABLE} SET abstract = abstract || ' {MARKER}' WHERE id = ANY(%s)", (upd_abs,))
    conn.execute(f"UPDATE {TABLE} SET title = 'Updated {TITLE_MARKER} ' || title WHERE id = ANY(%s)", (upd_title,))
    conn.execute(f"DELETE FROM {TABLE} WHERE id = ANY(%s)", (del_ids,))
    log("modify_in_postgres", abstract_updated=upd_abs, title_updated=upd_title, deleted=del_ids)

    before = verify(conn, upd_abs + upd_title, del_ids, "before_sync")   # oczekujemy rozbieżności
    res = sync(conn)
    after = verify(conn, upd_abs + upd_title, del_ids, "after_sync")     # oczekujemy zgodności

    revert(conn)
    sync(conn)
    restored = verify(conn, [r["id"] for r in recs], [], "after_revert")
    save_json(config.results_dir / "sync_log.json", {
        "timestamp": now(), "table": TABLE, "abstract_updated": upd_abs, "title_updated": upd_title, "deleted": del_ids,
        "mismatch_before_sync": not before["ok"], "consistent_after_sync": after["ok"],
        "restored_after_revert": restored["ok"], "sync_result": res, "log": LOG})
    return 0 if after["ok"] and restored["ok"] and not before["ok"] else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["demo", "sync", "revert"])
    args = ap.parse_args()
    with pg_connect(autocommit=True) as conn:
        if args.cmd == "demo":
            return demo(conn)
        setup(conn)
        if args.cmd == "revert":
            revert(conn)
        sync(conn)
    return 0


if __name__ == "__main__":
    sys.exit(main())

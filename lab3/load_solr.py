"""Etap 4: kolekcje Solra (papers_10/50/100), schemat z solr/schema.json i ładowanie przez /update.

Uruchomienie:  python -m lab3.load_solr [--sizes 10 50 100] [--data-dir KATALOG] [--batch 5000]

Dla każdej kolekcji: usunięcie starej (idempotentność) -> utworzenie z własnym configsetem lab3_<kolekcja> (kopia _default)
-> Config API (update.autoCreateFields=false, wyłączone auto(soft)commit) -> Schema API (solr/schema.json)
-> wysyłanie paczek JSON po N dokumentów na /update (bez commitu) -> JEDEN commit na końcu.
Po załadowaniu sprawdzamy numFound == liczba wierszy w tabeli Postgresa (jeśli tabela istnieje).
"""
import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import requests
from tqdm import tqdm

from lab3.config import ROOT, config
from lab3.solr import solr_get

# Schemat i konfiguracja w SolrCloud leżą w configsecie (ZooKeeper) współdzielonym przez wszystkie kolekcje,
# które go używają — dlatego każda kolekcja dostaje własny configset (kopia _default): lab3_<nazwa>.
SESSION = requests.Session()


def api(method: str, path: str, **kw):
    kw.setdefault("timeout", 600)
    r = SESSION.request(method, f"{config.solr_url}/{path.lstrip('/')}", **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
    return r.json()


def recreate_collection(name: str) -> None:
    if name in solr_get("admin/collections", action="LIST")["collections"]:
        solr_get("admin/collections", action="DELETE", name=name)
        print(f"Usunięto istniejącą kolekcję {name}")
    cs = f"lab3_{name}"
    if cs in solr_get("admin/configs", action="LIST")["configSets"]:
        solr_get("admin/configs", action="DELETE", name=cs)
    solr_get("admin/configs", action="CREATE", name=cs, baseConfigSet="_default")
    r = solr_get("admin/collections", action="CREATE", name=name, **{"collection.configName": cs},
                 numShards=1, replicationFactor=1)
    assert "failure" not in r, r
    for fname in ("collection_config.json", "schema.json"):
        body = json.loads((ROOT / "solr" / fname).read_text(encoding="utf-8"))
        endpoint = "config" if fname.startswith("collection_config") else "schema"
        res = api("POST", f"{name}/{endpoint}", json=body)
        if res.get("errors"):
            raise RuntimeError(res["errors"])
    print(f"Kolekcja {name} utworzona; Config API + Schema API zastosowane")


def index_file(name: str, path: Path, batch: int) -> dict:
    nbytes = path.stat().st_size
    sent = 0
    t_send = 0.0
    buf: list[str] = []

    def flush():
        nonlocal buf, sent, t_send
        if not buf:
            return
        body = ("[" + ",".join(buf) + "]").encode("utf-8")
        t0 = time.perf_counter()
        r = SESSION.post(f"{config.solr_url}/{name}/update?commit=false", data=body,
                         headers={"Content-Type": "application/json; charset=utf-8"}, timeout=600)
        t_send += time.perf_counter() - t0
        if r.status_code != 200:
            raise RuntimeError(f"/update -> {r.status_code}: {r.text[:500]}")
        sent += len(buf)
        buf = []

    with open(path, "r", encoding="utf-8") as f, tqdm(total=nbytes, unit="B", unit_scale=True, desc=f"Solr {name}") as bar:
        for line in f:
            bar.update(len(line.encode("utf-8")))
            line = line.strip()
            if line:
                buf.append(line)
            if len(buf) >= batch:
                flush()
        flush()
    t0 = time.perf_counter()
    api("GET", f"{name}/update", params={"commit": "true", "wt": "json"})
    commit_s = time.perf_counter() - t0
    return {"docs_sent": sent, "send_seconds": round(t_send, 2), "commit_seconds": round(commit_s, 2),
            "jsonl_bytes": nbytes}


def index_size_bytes(name: str) -> int:
    st = solr_get("admin/cores", action="STATUS")["status"]
    return sum(c["index"]["sizeInBytes"] for cn, c in st.items() if cn.startswith(name + "_shard"))


def num_found(name: str) -> int:
    return solr_get(f"{name}/select", q="*:*", rows=0)["response"]["numFound"]


def pg_rows(table: str):
    try:
        from lab3.db import pg_connect
        with pg_connect(connect_timeout=5) as conn:
            return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", nargs="+", default=["10", "50", "100"], choices=["10", "50", "100"])
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--batch", type=int, default=5000)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    data_dir = Path(args.data_dir) if args.data_dir else config.data_dir
    out = Path(args.out) if args.out else config.results_dir / "load_solr.json"

    results = []
    for size in args.sizes:
        name = f"papers_{size}"
        print(f"\n=== {name} ===")
        recreate_collection(name)
        t0 = time.perf_counter()
        res = {"collection": name, "batch_size": args.batch}
        res.update(index_file(name, data_dir / f"{name}.jsonl", args.batch))
        res["total_seconds"] = round(time.perf_counter() - t0, 2)
        res["num_found"] = num_found(name)
        res["pg_rows"] = pg_rows(name)
        res["index_bytes"] = index_size_bytes(name)
        res["counts_match"] = res["pg_rows"] is None or res["pg_rows"] == res["num_found"]
        print(f"wysyłanie {res['send_seconds']} s, commit {res['commit_seconds']} s, numFound={res['num_found']} "
              f"(PG: {res['pg_rows']}), indeks {res['index_bytes'] / 2**20:.0f} MiB")
        if res["num_found"] != res["docs_sent"]:
            raise RuntimeError(f"numFound {res['num_found']} != wysłano {res['docs_sent']}")
        results.append(res)
    info = solr_get("admin/info/system")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "solr_version": info["lucene"]["solr-spec-version"], "lucene_version": info["lucene"]["lucene-spec-version"],
        "jvm_max_heap_bytes": info["jvm"]["memory"]["raw"]["max"], "collections": results,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nZapisano {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

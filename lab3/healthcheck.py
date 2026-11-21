"""Sprawdzenie środowiska: PostgreSQL i Solr.

Uruchomienie: python -m lab3.healthcheck
Kod wyjścia: 0 gdy wszystko OK, 1 gdy jest błąd.
"""
import sys

import requests

from lab3.config import config
from lab3.db import pg_connect
from lab3.solr import solr_get


def ok(msg: str) -> None:
    print(f"  [OK]    {msg}")


def fail(msg: str, hint: str) -> None:
    print(f"  [BŁĄD]  {msg}\n          -> {hint}")


def check_postgres() -> bool:
    print(f"PostgreSQL ({config.pg_host}:{config.pg_port}, baza {config.pg_database})")
    try:
        conn = pg_connect(connect_timeout=5, autocommit=True)
    except Exception as exc:
        fail(
            f"nie można się połączyć: {exc}".strip(),
            "uruchom `docker compose up -d`, sprawdź PG_PORT/PG_USER/PG_PASSWORD w .env "
            "(port 5432 bywa zajęty przez inną instancję Postgresa — zmień PG_PORT i uruchom kontener ponownie)",
        )
        return False
    good = True
    with conn:
        version = conn.execute("SELECT version()").fetchone()[0]
        ok(version)
        try:
            # rozszerzenie tworzone w transakcji, którą wycofujemy — tylko test dostępności
            conn.autocommit = False
            conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
            conn.rollback()
            ok("rozszerzenie pg_trgm jest dostępne (można je utworzyć)")
        except Exception as exc:
            conn.rollback()
            fail(f"pg_trgm niedostępne: {exc}", "użyj oficjalnego obrazu postgres:17 (zawiera contrib)")
            good = False
    return good


def check_solr() -> bool:
    print(f"Solr ({config.solr_url})")
    try:
        info = solr_get("admin/info/system")
    except requests.RequestException as exc:
        fail(
            f"nie można się połączyć: {exc}",
            "uruchom `docker compose up -d` i poczekaj do statusu healthy (`docker compose ps`); sprawdź SOLR_PORT",
        )
        return False
    ok(f"wersja Solr {info['lucene']['solr-spec-version']} (Lucene {info['lucene']['lucene-spec-version']})")
    mode = info.get("mode")
    if mode == "solrcloud":
        ok("tryb pracy: SolrCloud (wbudowany ZooKeeper) — Configsets API i Collections API dostępne")
    else:
        fail(f"tryb pracy: {mode}", "potrzebny SolrCloud (kolekcje z własnym configsetem); uruchom Solra z opcją -c")
        return False
    mem = info["jvm"]["memory"]
    ok(f"heap JVM: max {mem['raw']['max'] / 2**30:.1f} GB, użyte {mem['used']}")
    try:
        collections = solr_get("admin/collections", action="LIST")["collections"]
        ok(f"kolekcje: {', '.join(collections) if collections else '(brak)'}")
        configsets = solr_get("admin/configs", action="LIST")["configSets"]
        ok(f"configsety: {', '.join(configsets)}")
    except requests.RequestException as exc:
        fail(f"błąd Collections/Configsets API: {exc}", "sprawdź logi: `docker compose logs solr`")
        return False
    return True


def main() -> int:
    results = [check_postgres(), check_solr()]
    print()
    if all(results):
        print("Środowisko gotowe.")
        return 0
    print("Środowisko wymaga poprawek — patrz komunikaty [BŁĄD] powyżej.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

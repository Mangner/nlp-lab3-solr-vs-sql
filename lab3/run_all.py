"""Jeden punkt wejścia: uruchamia wszystkie etapy projektu po kolei.

Uruchomienie (z katalogu głównego, po `docker compose up -d`):
    python -m lab3.run_all                       # całość (pełny zbiór, ok. 1,5–2 godziny)
    python -m lab3.run_all --limit 20000         # szybki test na małej próbce (zbiór 100% = 20 000 rekordów)
    python -m lab3.run_all --skip prepare load_pg load_solr   # pomiń kroki (np. dane już załadowane)
    python -m lab3.run_all --only figures report pdf          # tylko wybrane kroki
    python -m lab3.run_all --with-cold           # dodatkowo pomiar zimnego startu (restartuje kontenery!)

Kroki (kolejność ma znaczenie — `sync` zmienia i przywraca dane, więc działa po pomiarach):
    healthcheck, prepare, load_pg, load_solr, level3, bench, level4, facets, paging, sync, [cold], environment, figures, report, pdf
Każdy krok jest idempotentny (tabele i kolekcje są tworzone od nowa). Przy błędzie kroku przerywamy z kodem != 0.
"""
import argparse
import subprocess
import sys
import time

from lab3.config import ROOT

STEPS = {
    "healthcheck": ["-m", "lab3.healthcheck"],
    "prepare": ["-m", "lab3.prepare_data"],
    "load_pg": ["-m", "lab3.load_pg"],
    "load_solr": ["-m", "lab3.load_solr"],
    "level3": ["-m", "lab3.level3"],
    "bench": ["-m", "lab3.bench"],
    "level4": ["-m", "lab3.level4"],
    "facets": ["-m", "lab3.facets"],
    "paging": ["-m", "lab3.paging"],
    "sync": ["-m", "lab3.sync", "demo"],
    "cold": ["-m", "lab3.cold", "--drop-vm-cache"],
    "environment": ["-m", "lab3.environment"],
    "figures": ["-m", "lab3.figures"],
    "report": ["-m", "lab3.report"],
    "pdf": ["scripts/build_pdf.py"],
}
DEFAULT = [s for s in STEPS if s != "cold"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip", nargs="*", default=[], choices=list(STEPS))
    ap.add_argument("--only", nargs="*", default=None, choices=list(STEPS))
    ap.add_argument("--with-cold", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="liczba rekordów zbioru 100%% (test na próbce)")
    args = ap.parse_args()
    steps = args.only if args.only else [s for s in STEPS if s in DEFAULT or (s == "cold" and args.with_cold)]
    steps = [s for s in steps if s not in args.skip]
    t_all = time.time()
    for s in steps:
        cmd = [sys.executable, *STEPS[s]]
        if s == "prepare" and args.limit:
            cmd += ["--limit", str(args.limit)]
        print(f"\n########## {s}: {' '.join(cmd[1:])}", flush=True)
        t0 = time.time()
        r = subprocess.run(cmd, cwd=ROOT)
        print(f"########## {s}: kod {r.returncode}, {time.time() - t0:.0f} s", flush=True)
        if r.returncode != 0:
            print(f"Krok '{s}' zakończył się błędem — przerywam. Wznów: python -m lab3.run_all --only ... (kolejne kroki)")
            return r.returncode
    print(f"\nGotowe w {(time.time() - t_all) / 60:.1f} min.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

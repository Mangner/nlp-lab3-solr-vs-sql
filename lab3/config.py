"""Konfiguracja projektu wczytywana z pliku .env (python-dotenv)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Config:
    pg_host: str = _env("PG_HOST", "localhost")
    pg_port: int = int(_env("PG_PORT", "5432"))
    pg_user: str = _env("PG_USER", "lab3")
    pg_password: str = _env("PG_PASSWORD", "lab3")
    pg_database: str = _env("PG_DATABASE", "lab3")

    solr_host: str = _env("SOLR_HOST", "localhost")
    solr_port: int = int(_env("SOLR_PORT", "8983"))

    num_records: int = int(_env("NUM_RECORDS", "1000000"))
    random_seed: int = int(_env("RANDOM_SEED", "42"))
    data_dir: Path = ROOT / _env("DATA_DIR", "data")
    results_dir: Path = ROOT / _env("RESULTS_DIR", "results")

    @property
    def pg_dsn(self) -> str:
        return (
            f"host={self.pg_host} port={self.pg_port} dbname={self.pg_database} "
            f"user={self.pg_user} password={self.pg_password}"
        )

    @property
    def solr_url(self) -> str:
        return f"http://{self.solr_host}:{self.solr_port}/solr"


config = Config()

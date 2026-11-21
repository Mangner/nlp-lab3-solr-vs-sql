"""Wspólny helper do PostgreSQL."""
import psycopg

from lab3.config import config


def pg_connect(**kwargs) -> psycopg.Connection:
    return psycopg.connect(config.pg_dsn, **kwargs)

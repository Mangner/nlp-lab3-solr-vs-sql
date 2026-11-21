"""Wspólny helper do Solra (HTTP przez requests)."""
import requests

from lab3.config import config

TIMEOUT = 30


def solr_get(path: str, **params) -> dict:
    """GET na {solr_url}/{path} z wymuszonym wt=json; zwraca sparsowany JSON."""
    params.setdefault("wt", "json")
    resp = requests.get(f"{config.solr_url}/{path.lstrip('/')}", params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()

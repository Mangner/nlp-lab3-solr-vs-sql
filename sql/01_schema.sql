-- Schemat tabeli zbioru arXiv w PostgreSQL.
-- Plik jest SZABLONEM: {t} = papers_10 | papers_50 | papers_100 (podstawia lab3.load_pg).
-- Ręcznie w psql: sed 's/{t}/papers_100/g' sql/01_schema.sql | psql ...
-- Kolumna tsv jest GENERATED ... STORED: tsvector (konfiguracja 'english', tytuł z wagą A, abstrakt z wagą B)
-- liczy się automatycznie przy INSERT/COPY/UPDATE, więc nie da się go "zapomnieć" zsynchronizować.
-- Indeksów (GIN, B-tree) NIE tworzymy tutaj — powstają po załadowaniu danych (sql/02_indexes.sql).
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- tylko do eksperymentów; NIE zakładamy indeksu gin_trgm_ops na tekście

DROP TABLE IF EXISTS {t} CASCADE;
CREATE TABLE {t} (
    id               text PRIMARY KEY,          -- identyfikator arXiv, np. 0704.0001 albo hep-th/9812056
    title            text NOT NULL,
    abstract         text NOT NULL,
    primary_category text NOT NULL,             -- pierwsza kategoria z listy categories, np. astro-ph.GA
    archive          text NOT NULL,             -- część primary_category przed kropką, np. astro-ph
    categories       text[] NOT NULL,
    year             integer NOT NULL,          -- rok pierwszej wersji
    license          text NOT NULL,             -- URL licencji albo 'none'
    updated_at       timestamptz NOT NULL DEFAULT now(),
    tsv              tsvector GENERATED ALWAYS AS (
                         setweight(to_tsvector('english', title), 'A') ||
                         setweight(to_tsvector('english', abstract), 'B')
                     ) STORED
);

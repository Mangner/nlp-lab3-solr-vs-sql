-- Indeksy tabeli {t} (szablon jak w 01_schema.sql). Tworzone PO załadowaniu danych (szybciej niż przy COPY).
-- @gin
CREATE INDEX {t}_tsv_gin ON {t} USING gin (tsv);
-- @btree_year
CREATE INDEX {t}_year_idx ON {t} (year);
-- @btree_category
CREATE INDEX {t}_primary_category_idx ON {t} (primary_category);
-- @analyze
ANALYZE {t};

-- Śledzenie zmian pod synchronizację z Solrem (szablon: {t}, patrz lab3.sync).
--  * updated_at jest ustawiane triggerem BEFORE UPDATE (zmiana jakiegokolwiek pola),
--  * usunięcia trafiają do tabeli {t}_deleted (trigger AFTER DELETE),
--  * sync_state({tbl}) pamięta moment ostatniej synchronizacji.
-- @setup
CREATE TABLE IF NOT EXISTS {t}_deleted (id text NOT NULL, deleted_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE IF NOT EXISTS sync_state (tbl text PRIMARY KEY, last_sync timestamptz NOT NULL);
CREATE OR REPLACE FUNCTION {t}_touch() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at := clock_timestamp(); RETURN NEW; END $$;
CREATE OR REPLACE FUNCTION {t}_log_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN INSERT INTO {t}_deleted (id) VALUES (OLD.id); RETURN OLD; END $$;
DROP TRIGGER IF EXISTS {t}_touch_trg ON {t};
CREATE TRIGGER {t}_touch_trg BEFORE UPDATE ON {t} FOR EACH ROW EXECUTE FUNCTION {t}_touch();
DROP TRIGGER IF EXISTS {t}_delete_trg ON {t};
CREATE TRIGGER {t}_delete_trg AFTER DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION {t}_log_delete();
CREATE INDEX IF NOT EXISTS {t}_updated_at_idx ON {t} (updated_at);
-- @teardown
DROP TRIGGER IF EXISTS {t}_touch_trg ON {t};
DROP TRIGGER IF EXISTS {t}_delete_trg ON {t};
DROP INDEX IF EXISTS {t}_updated_at_idx;
DROP TABLE IF EXISTS {t}_deleted;
DELETE FROM sync_state WHERE tbl = '{t}';

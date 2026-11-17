"""RAISE NOTICE из миграции данных попадает в журнал службы строкой «MIGRATION <файл>: NOTICE …»."""
from artgame import db


def test_migration_notice_goes_to_log(client, tmp_path, monkeypatch, capsys):
    (tmp_path / "999_notice.sql").write_text("DO $$ BEGIN RAISE NOTICE 'сделка 1: пропуск'; END $$;")
    monkeypatch.setattr(db, "MIGRATIONS", tmp_path)
    try:
        assert db.migrate(db.pool) == ["999_notice.sql"]
        assert "MIGRATION 999_notice.sql: NOTICE сделка 1: пропуск" in capsys.readouterr().err
    finally:
        with db.pool.connection() as conn:
            conn.execute("DELETE FROM schema_migrations WHERE name = '999_notice.sql'")

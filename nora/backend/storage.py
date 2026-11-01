"""Queue storage with a session-wide PostgreSQL controller lock.

PostgreSQL requires a direct session connection (no transaction-pooling proxy).
There is deliberately no reconnect: a lost session must never lose ownership
silently while the process continues dispatching inference.
"""
import os
import re
import sqlite3

LOCK_KEY = 0x4e4f524153545544
SCHEMA = (
    'CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,name TEXT,mime TEXT,path TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,status TEXT NOT NULL,created_at TEXT,updated_at TEXT,payload TEXT NOT NULL,result TEXT,error TEXT,progress TEXT,cancel_requested INTEGER DEFAULT 0{sequence})',
    'CREATE TABLE IF NOT EXISTS studio_imports(source_sha256 TEXT PRIMARY KEY,imported_at TEXT NOT NULL,counts TEXT NOT NULL)',
)


class Row(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


def row_factory(cursor):
    names = [column.name for column in cursor.description or ()]
    return lambda values: Row(zip(names, values))


class Postgres:
    dialect = 'postgresql'

    def __init__(self, url):
        import psycopg
        try:
            self.connection = psycopg.connect(url, autocommit=True, row_factory=row_factory, connect_timeout=10)
        except (psycopg.Error, ValueError):
            raise RuntimeError('PostgreSQL connection failed; controller was not started') from None
        try:
            owned = self.connection.execute('SELECT pg_try_advisory_lock(%s)', (LOCK_KEY,)).fetchone()[0]
            if not owned:
                raise RuntimeError('Another Studio controller already owns this database')
        except BaseException:
            self.connection.close()
            raise

    def execute(self, sql, params=()):
        # All SQL is maintained application SQL; reference data stays bound.
        sql = re.sub(r'\browid\b', 'sequence', sql)
        sql = sql.replace('?', '%s')
        if sql.lstrip().split(None, 1)[0].upper() in {'INSERT','UPDATE','DELETE'}:
            if self.connection.info.transaction_status == 0:
                self.connection.execute('BEGIN')
        return self.connection.execute(sql, params)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        self.connection.close()


def connect(root, database_url=None, initialize=True):
    url = os.environ.get('DATABASE_URL', '') if database_url is None else database_url
    if url:
        if not url.startswith(('postgres://', 'postgresql://')):
            raise ValueError('DATABASE_URL must use PostgreSQL')
        db = Postgres(url)
    else:
        db = sqlite3.connect(root / 'queue.sqlite3', check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
    if initialize:
        try:
            for statement in SCHEMA:
                db.execute(statement.format(sequence=',sequence BIGSERIAL UNIQUE' if url else ''))
            db.commit()
        except BaseException:
            db.close()
            raise
    return db

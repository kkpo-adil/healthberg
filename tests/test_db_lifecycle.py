"""SQLite connection must close deterministically on CPython 3.14/macOS."""
import sqlite3
from app import db


def test_connection_closed_on_context_exit(client):
    with db.connect() as conn:
        assert conn.execute('SELECT 1').fetchone()[0] == 1
    try:
        conn.execute('SELECT 1')
    except sqlite3.ProgrammingError as e:
        assert 'closed' in str(e).lower()
    else:
        raise AssertionError('sqlite3 connection leaked: context exit left connection open')


def test_connection_closed_when_query_raises(client):
    try:
        with db.connect() as conn:
            conn.execute('SELECT * FROM this_table_does_not_exist')
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError('Expected missing table exception')
    try:
        conn.execute('SELECT 1')
    except sqlite3.ProgrammingError:
        pass
    else:
        raise AssertionError('sqlite3 connection leaked after exception')


def test_many_consecutive_database_connections(client):
    for _ in range(1000):
        with db.connect() as conn:
            assert conn.execute('SELECT 1').fetchone()[0] == 1

"""Erase content in active SQLite files; not a forensic disk/backups guarantee."""
import os
from pathlib import Path
import sqlite3


def private_deletes(connection):
    try:
        connection.execute('PRAGMA secure_delete=ON')
    except BaseException:
        connection.close()
        raise
    return connection


def checkpoint_erasure(connection):
    """Call after commit; refuse a success claim if old WAL frames are pinned."""
    if connection.in_transaction:
        raise sqlite3.ProgrammingError('Erasure must be committed before checkpoint')
    result = connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
    if result and result[0]:
        raise sqlite3.OperationalError('Effacement incomplet : journal SQLite encore occupe.')


def prepare_private_file(path):
    """Owner-only folder (0700) and database file (0600), created if missing."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if not path.exists():
        path.touch(mode=0o600)
    os.chmod(path, 0o600)


def open_private_db(path, timeout=5.0, prepare=True):
    """Open a private local SQLite database the one way every store should.

    Owner-only rights (unless `prepare` is False because the caller already
    did it for this path), secure deletion, Row results. The schema stays
    with each store.
    """
    if prepare:
        prepare_private_file(path)
    connection = private_deletes(sqlite3.connect(path, timeout=timeout))
    connection.row_factory = sqlite3.Row
    return connection

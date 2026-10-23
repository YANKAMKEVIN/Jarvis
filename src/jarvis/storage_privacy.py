"""Erase content in active SQLite files; not a forensic disk/backups guarantee."""
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

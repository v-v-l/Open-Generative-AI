#!/usr/bin/env python3
"""Offline, atomic SQLite -> empty PostgreSQL migration. Copies no media files."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

import storage

SOURCE_COLUMNS = {
    'settings': ('key','value'),
    'assets': ('id','name','mime','path'),
    'jobs': ('id','status','created_at','updated_at','payload','result','error','progress','cancel_requested'),
}


class MigrationError(ValueError):
    """Safe operator-facing migration precondition failure."""


def import_queue(source_root, target_root, database_url, original_root=None):
    source_root, target_root = Path(source_root).resolve(), Path(target_root).resolve()
    # An offline snapshot copied to another host retains the old absolute paths.
    path_root = Path(original_root).resolve() if original_root else source_root
    lock = (source_root / 'server.lock').open('a')
    source = target = None
    try:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise MigrationError('Stop the source Studio controller before migration') from None
        source = sqlite3.connect((source_root / 'queue.sqlite3').as_uri()+'?mode=ro', uri=True)
        source.row_factory = sqlite3.Row
        source.execute('BEGIN')
        for name, expected in SOURCE_COLUMNS.items():
            columns = tuple(row[1] for row in source.execute('PRAGMA table_info('+name+')'))
            if columns != expected:
                raise MigrationError('Unsupported source queue schema; migration was not started')
        paused = source.execute("SELECT value FROM settings WHERE key='queue_paused'").fetchone()
        if not paused or paused[0] != 'true' or source.execute("SELECT COUNT(*) FROM jobs WHERE status='running'").fetchone()[0]:
            raise MigrationError('Source must be paused with no running jobs')
        tables = {name:[dict(row) for row in source.execute('SELECT * FROM '+name+(' ORDER BY rowid' if name=='jobs' else ' ORDER BY '+('key' if name=='settings' else 'id')))] for name in ('settings','assets','jobs')}
        digest = hashlib.sha256(json.dumps(tables,sort_keys=True).encode()).hexdigest()
        counts = {name:len(rows) for name,rows in tables.items()}
        # Rewrite only registered media paths, after validating their old boundary.
        for asset in tables['assets']:
            path = Path(asset['path']).resolve()
            if not path.is_relative_to(path_root):
                raise MigrationError('Source contains an asset outside its storage root')
            replacement = target_root / path.relative_to(path_root)
            if not replacement.resolve().is_relative_to(target_root):
                raise MigrationError('Target asset path escapes storage root')
            if not replacement.is_file():
                raise MigrationError('Copy all source media files to target root before migration')
            asset['path'] = str(replacement)
        target = storage.connect(target_root, database_url)
        target.connection.execute('BEGIN')
        target.connection.execute('LOCK TABLE settings,assets,jobs,studio_imports IN ACCESS EXCLUSIVE MODE')
        for name in ('settings','assets','jobs','studio_imports'):
            if target.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]:
                raise MigrationError('Target database is not empty; refusing to overwrite')
        for name, rows in tables.items():
            for row in rows:
                columns = list(row)
                target.execute('INSERT INTO '+name+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')', tuple(row.values()))
        actual = {name:target.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in tables}
        if actual != counts:
            raise RuntimeError('Migration row counts did not match')
        target.execute('INSERT INTO studio_imports VALUES(?,?,?)', (digest,time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),json.dumps(counts)))
        target.commit()
        return {'source_sha256':digest,'counts':actual,'queue_paused':True}
    except BaseException:
        if target: target.rollback()
        raise
    finally:
        if source: source.close()
        if target: target.close()
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--target-root',type=Path,required=True)
    parser.add_argument('--original-root',type=Path,help='Original absolute storage root recorded in an offline copied snapshot; stop the original controller before copying')
    args = parser.parse_args()
    try:
        url = os.environ.get('DATABASE_URL','')
        if not url: raise MigrationError('Set DATABASE_URL locally; never pass credentials as CLI arguments')
        print(json.dumps(import_queue(args.source_root,args.target_root,url,args.original_root)))
    except Exception as exc:
        # Driver errors may include DSNs; print only a known safe explanation.
        parser.exit(1, str(exc)+'\n' if isinstance(exc,MigrationError) else 'Migration failed; no partial import was committed. Check database connectivity.\n')


if __name__ == '__main__': main()

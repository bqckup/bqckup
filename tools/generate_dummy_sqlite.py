#!/usr/bin/env python3
"""Generate a large SQLite database for testing backups.

Usage examples:
  python tools/generate_dummy_sqlite.py --db /tmp/large.db --rows 1000000
  python tools/generate_dummy_sqlite.py --db /tmp/test.db --rows 1000
"""
import argparse
import sqlite3
import time
import random
import string
import os
import sys


def random_text(length=100):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def generate(db_path: str, rows: int, batch: int = 10000):
    os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('PRAGMA synchronous = OFF')
    cur.execute('PRAGMA journal_mode = MEMORY')
    cur.execute('CREATE TABLE IF NOT EXISTS bigdata (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, payload TEXT, created INTEGER)')
    conn.commit()

    inserted = 0
    start = time.time()
    try:
        while inserted < rows:
            to_insert = min(batch, rows - inserted)
            now_ts = int(time.time())
            batch_data = [(f'name-{inserted + i}-{random_text(8)}', random_text(256), now_ts) for i in range(to_insert)]
            cur.executemany('INSERT INTO bigdata (name,payload,created) VALUES (?,?,?)', batch_data)
            conn.commit()
            inserted += to_insert
            elapsed = time.time() - start
            rate = inserted / elapsed if elapsed > 0 else 0
            print(f"Inserted {inserted}/{rows} rows — elapsed {int(elapsed)}s — ~{int(rate)}/s")
            sys.stdout.flush()
    except KeyboardInterrupt:
        print('\nInterrupted by user')
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Generate large sqlite DB for backup testing')
    parser.add_argument('--db', '-d', default='/tmp/large_dummy.db', help='Output sqlite file')
    parser.add_argument('--rows', '-r', type=int, default=1000000, help='Number of rows to insert')
    parser.add_argument('--batch', type=int, default=10000, help='Batch insert size')
    args = parser.parse_args()

    print(f"Generating DB {args.db} with {args.rows} rows (batch {args.batch})")
    generate(args.db, args.rows, args.batch)


if __name__ == '__main__':
    main()

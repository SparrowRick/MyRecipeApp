"""Create a consistent SQLite backup plus an uploads archive."""
import argparse
import datetime
import os
import shutil
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def create_backup(output_dir, keep=14):
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    database_source = ROOT / 'recipes.db'
    database_target = output_dir / f'recipes_{stamp}.db'
    with sqlite3.connect(database_source) as source, sqlite3.connect(database_target) as target:
        source.backup(target)
    uploads = ROOT / 'static' / 'uploads'
    if uploads.exists():
        shutil.make_archive(str(output_dir / f'uploads_{stamp}'), 'zip', uploads)
    backups = sorted(output_dir.glob('recipes_*.db'), key=os.path.getmtime, reverse=True)
    for old_database in backups[keep:]:
        suffix = old_database.stem.removeprefix('recipes_')
        old_database.unlink(missing_ok=True)
        (output_dir / f'uploads_{suffix}.zip').unlink(missing_ok=True)
    print(database_target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'backups')
    parser.add_argument('--keep', type=int, default=14)
    args = parser.parse_args()
    create_backup(args.output, max(1, args.keep))

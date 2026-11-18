from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def data_dir() -> Path:
    root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    path = root / "update-watch"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


DB_ROOT = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "update-watch"
DB_PATH = DB_ROOT / "update-watch.sqlite3"


@contextmanager
def connect(path: Path | str | None = DB_PATH) -> Iterator[sqlite3.Connection]:
    target = DB_PATH if path is None else path
    Path(target).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(target, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize(path: Path | str = DB_PATH) -> None:
    with connect(path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, kind TEXT NOT NULL,
          url TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
          last_sync TEXT, last_error TEXT
        );
        CREATE TABLE IF NOT EXISTS publications (
          id INTEGER PRIMARY KEY, source_id INTEGER REFERENCES sources(id),
          external_id TEXT, title TEXT NOT NULL, content TEXT NOT NULL DEFAULT '',
          author TEXT NOT NULL DEFAULT '', published_at TEXT, url TEXT NOT NULL UNIQUE,
          category TEXT NOT NULL DEFAULT 'general', read INTEGER NOT NULL DEFAULT 0,
          favorite INTEGER NOT NULL DEFAULT 0, resolution TEXT NOT NULL DEFAULT 'unknown',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS packages (
          name TEXT PRIMARY KEY, installed_version TEXT, available_version TEXT,
          repository TEXT NOT NULL DEFAULT '', download_size INTEGER,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS analyses (
          id INTEGER PRIMARY KEY, package_name TEXT NOT NULL, risk TEXT NOT NULL,
          report_count INTEGER NOT NULL, summary TEXT NOT NULL, publication_ids TEXT NOT NULL,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS update_history (
          id INTEGER PRIMARY KEY, package_name TEXT NOT NULL, installed_version TEXT,
          available_version TEXT, detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          status TEXT NOT NULL DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS system_operations (
          id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
          started_at TEXT NOT NULL, finished_at TEXT, exit_code INTEGER, detail TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_publications_date ON publications(published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_publications_source ON publications(source_id);
        CREATE INDEX IF NOT EXISTS idx_analyses_package ON analyses(package_name, created_at DESC);
        """)
        publication_columns = {row[1] for row in db.execute("PRAGMA table_info(publications)")}
        if "resolution" not in publication_columns:
            db.execute("ALTER TABLE publications ADD COLUMN resolution TEXT NOT NULL DEFAULT 'unknown'")
        package_columns = {row[1] for row in db.execute("PRAGMA table_info(packages)")}
        if "download_size" not in package_columns:
            db.execute("ALTER TABLE packages ADD COLUMN download_size INTEGER")
        defaults = [
          ("CachyOS Forum", "discourse", "https://discuss.cachyos.org"),
          ("Reddit CachyOS", "reddit", "https://www.reddit.com/r/cachyos/.rss"),
          ("CachyOS GitHub", "github", "https://api.github.com/orgs/CachyOS"),
          ("CachyOS Distribution Issues", "github_repo", "https://github.com/CachyOS/distribution/issues"),
          ("Mesa Issues", "gitlab", "https://gitlab.freedesktop.org/mesa/mesa/-/issues"),
          ("AMD GPU Driver Issues", "github_repo", "https://github.com/ROCm/amdgpu/issues"),
          ("Arch News", "rss", "https://archlinux.org/feeds/news/"),
        ]
        db.executemany("INSERT OR IGNORE INTO sources(name,kind,url) VALUES(?,?,?)", defaults)


def rows(query: str, params: tuple = (), path: Path | str = DB_PATH) -> list[dict]:
    with connect(path) as db:
        return [dict(row) for row in db.execute(query, params).fetchall()]

"""Datenbankzugriff auf die Anthias-SQLite-DB.

Lese- und Schreiboperationen fuer Assets.
"""

import sqlite3
from datetime import datetime, timezone

from displaywall.config import DB_PATH, DISPLAY_PREFIX


def get_assets():
    """Alle Assets aus der DB lesen (fuer Web-GUI)."""
    if not DB_PATH.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT asset_id, name, uri, mimetype, duration, is_enabled, play_order "
            "FROM assets ORDER BY play_order ASC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []


def get_playlist(prefix=DISPLAY_PREFIX):
    """Aktive Assets mit gegebenem Prefix laden (fuer Viewer)."""
    if not DB_PATH.exists():
        return []

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """
            SELECT name, uri, mimetype, duration, play_order
            FROM assets
            WHERE is_enabled = 1
              AND is_processing = 0
              AND name LIKE ?
              AND start_date <= ?
              AND end_date >= ?
            ORDER BY play_order ASC
            """,
            (f"{prefix}%", now, now),
        )
        assets = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return assets
    except sqlite3.Error:
        return []


def move_asset(asset_id, target):
    """Asset einem Display zuweisen (setzt/entfernt Prefix im Namen).

    target: 1 = Display 1 (Prefix entfernen), 2 = Display 2 (Prefix setzen)
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT name FROM assets WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        if not row:
            conn.close()
            return False

        name = row[0]
        if target == 2 and not name.startswith(DISPLAY_PREFIX):
            new_name = DISPLAY_PREFIX + name
        elif target == 1 and name.startswith(DISPLAY_PREFIX):
            new_name = name[len(DISPLAY_PREFIX):]
        else:
            conn.close()
            return True

        conn.execute(
            "UPDATE assets SET name = ? WHERE asset_id = ?",
            (new_name, asset_id),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error:
        return False


def add_asset(asset_id, name, uri, mimetype, duration=10):
    """Neues Asset in die DB eintragen."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        far_future = "2099-01-01T00:00:00+00:00"
        conn.execute(
            """
            INSERT INTO assets
                (asset_id, name, uri, mimetype, duration, is_enabled, is_processing,
                 nocache, play_order, start_date, end_date, skip_asset_check)
            VALUES (?, ?, ?, ?, ?, 1, 0, 0, 0, ?, ?, 0)
            """,
            (asset_id, name, uri, mimetype, duration, now, far_future),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error:
        return False


def get_db_mtime():
    """Aenderungszeitpunkt der Datenbank (fuer Change-Detection)."""
    try:
        return DB_PATH.stat().st_mtime
    except OSError:
        return 0

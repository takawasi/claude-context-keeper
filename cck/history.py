"""CCK History tracking - File changes and operations logging."""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize history database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    conn.execute('''
        CREATE TABLE IF NOT EXISTS file_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,  -- 'created' | 'modified' | 'deleted'
            file_path TEXT NOT NULL,
            snippet TEXT  -- First few lines for context
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            operation_type TEXT NOT NULL,  -- 'Bash' | 'Read' | 'Edit' | 'Task' | etc
            summary TEXT NOT NULL
        )
    ''')

    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_file_changes_timestamp
        ON file_changes(timestamp DESC)
    ''')

    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_operations_timestamp
        ON operations(timestamp DESC)
    ''')

    conn.commit()
    return conn


def log_file_change(conn: sqlite3.Connection, event_type: str, file_path: str, snippet: str = None):
    """Log a file change event."""
    timestamp = datetime.now().isoformat()
    conn.execute(
        'INSERT INTO file_changes (timestamp, event_type, file_path, snippet) VALUES (?, ?, ?, ?)',
        (timestamp, event_type, file_path, snippet)
    )
    conn.commit()


def log_operation(conn: sqlite3.Connection, operation_type: str, summary: str):
    """Log an operation."""
    timestamp = datetime.now().isoformat()
    conn.execute(
        'INSERT INTO operations (timestamp, operation_type, summary) VALUES (?, ?, ?)',
        (timestamp, operation_type, summary)
    )
    conn.commit()


def get_recent_changes(conn: sqlite3.Connection, limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent file changes."""
    cursor = conn.execute(
        'SELECT * FROM file_changes ORDER BY timestamp DESC LIMIT ?',
        (limit,)
    )
    return [dict(row) for row in cursor.fetchall()]


def get_recent_operations(conn: sqlite3.Connection, limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent operations."""
    cursor = conn.execute(
        'SELECT * FROM operations ORDER BY timestamp DESC LIMIT ?',
        (limit,)
    )
    return [dict(row) for row in cursor.fetchall()]


def get_combined_history(conn: sqlite3.Connection, limit: int = 20) -> List[Dict[str, Any]]:
    """Get combined history of file changes and operations, sorted by time."""
    # Get file changes
    changes = get_recent_changes(conn, limit)
    for c in changes:
        c['category'] = 'file'

    # Get operations
    ops = get_recent_operations(conn, limit)
    for o in ops:
        o['category'] = 'operation'

    # Combine and sort
    combined = changes + ops
    combined.sort(key=lambda x: x['timestamp'], reverse=True)

    return combined[:limit]


def format_history_compact(history: List[Dict[str, Any]]) -> str:
    """Format history in compact form for reminder injection."""
    lines = []
    for item in history:
        ts = item['timestamp'][11:19]  # Extract HH:MM:SS
        if item['category'] == 'file':
            event_map = {'created': '+', 'modified': '~', 'deleted': '-'}
            symbol = event_map.get(item['event_type'], '?')
            lines.append(f"{ts} {symbol} {item['file_path']}")
        else:
            lines.append(f"{ts} $ {item['operation_type']}: {item['summary'][:40]}")

    return '\n'.join(lines)


def format_history_detailed(history: List[Dict[str, Any]]) -> str:
    """Format history in detailed form."""
    lines = []
    for item in history:
        ts = item['timestamp'][:19].replace('T', ' ')
        if item['category'] == 'file':
            lines.append(f"[{ts}] File {item['event_type']}: {item['file_path']}")
            if item.get('snippet'):
                lines.append(f"  > {item['snippet'][:80]}")
        else:
            lines.append(f"[{ts}] {item['operation_type']}: {item['summary']}")

    return '\n'.join(lines)


def cleanup_old_entries(conn: sqlite3.Connection, max_entries: int = 1000):
    """Remove old entries beyond max_entries."""
    conn.execute('''
        DELETE FROM file_changes WHERE id NOT IN (
            SELECT id FROM file_changes ORDER BY timestamp DESC LIMIT ?
        )
    ''', (max_entries,))

    conn.execute('''
        DELETE FROM operations WHERE id NOT IN (
            SELECT id FROM operations ORDER BY timestamp DESC LIMIT ?
        )
    ''', (max_entries,))

    conn.commit()

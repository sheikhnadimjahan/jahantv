import sqlite3
import os
import json
import uuid
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "iptv_platform.db")

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Submissions table (Community suggestions, documentaries, corrections, partnerships)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            organization TEXT,
            title TEXT NOT NULL,
            details TEXT NOT NULL,
            source_url TEXT,
            country TEXT DEFAULT '',
            content_language TEXT DEFAULT 'English',
            rights_confirmed INTEGER DEFAULT 0,
            moderation_note TEXT DEFAULT '',
            copyright_declaration INTEGER DEFAULT 1,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    submission_columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(submissions)").fetchall()
    }
    for column_name, column_definition in (
        ("country", "TEXT DEFAULT ''"),
        ("content_language", "TEXT DEFAULT 'English'"),
        ("rights_confirmed", "INTEGER DEFAULT 0"),
        ("moderation_note", "TEXT DEFAULT ''"),
    ):
        if column_name not in submission_columns:
            cursor.execute(
                f"ALTER TABLE submissions ADD COLUMN {column_name} {column_definition}"
            )

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submission_reports (
            submission_id TEXT NOT NULL,
            reporter_fingerprint TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (submission_id, reporter_fingerprint)
        )
    ''')
    
    # User interaction table (Favorites, Watchlist, Recently Watched)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_session TEXT NOT NULL,
            item_type TEXT NOT NULL, -- 'channel' or 'vod'
            item_id TEXT NOT NULL,
            interaction_type TEXT NOT NULL, -- 'favorite', 'watchlist', 'history'
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_session, item_type, item_id, interaction_type)
        )
    ''')
    
    # Federation Node registrations
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS federated_nodes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            operator TEXT NOT NULL,
            endpoint_url TEXT NOT NULL,
            region TEXT NOT NULL,
            channels_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending_verification',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def save_submission(
    sub_type,
    name,
    email,
    phone,
    organization,
    title,
    details,
    source_url,
    country="",
    content_language="English",
    rights_confirmed=False,
    moderation_note="",
    status="pending",
):
    sub_id = f"DJ-{datetime.now().strftime('%Y%m')}-{uuid.uuid4().hex[:6].upper()}"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO submissions (
            id, type, name, email, phone, organization, title, details, source_url,
            country, content_language, rights_confirmed, moderation_note,
            copyright_declaration, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        sub_id,
        sub_type,
        name,
        email,
        phone,
        organization,
        title,
        details,
        source_url,
        country,
        content_language,
        int(bool(rights_confirmed)),
        moderation_note,
        int(bool(rights_confirmed)),
        status,
    ))
    conn.commit()
    conn.close()
    return sub_id

def get_submissions(limit=50):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM submissions ORDER BY created_at DESC LIMIT ?', (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_published_video_submissions(limit=100):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM submissions WHERE type = 'documentary_submission' "
        "AND status = 'published' ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def report_submission(submission_id, reporter_fingerprint, hide_threshold=1):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM submissions WHERE id = ? AND type = 'documentary_submission' "
        "AND status = 'published'",
        (submission_id,),
    )
    if cursor.fetchone() is None:
        conn.close()
        return None

    cursor.execute(
        "INSERT OR IGNORE INTO submission_reports (submission_id, reporter_fingerprint) "
        "VALUES (?, ?)",
        (submission_id, reporter_fingerprint),
    )
    cursor.execute(
        "SELECT COUNT(*) FROM submission_reports WHERE submission_id = ?",
        (submission_id,),
    )
    report_count = cursor.fetchone()[0]
    is_hidden = report_count >= hide_threshold
    if is_hidden:
        cursor.execute(
            "UPDATE submissions SET status = 'hidden' WHERE id = ?",
            (submission_id,),
        )
    conn.commit()
    conn.close()
    return {"report_count": report_count, "hidden": is_hidden}

def save_node_registration(name, operator, endpoint_url, region, channels_count):
    node_id = f"NODE-{uuid.uuid4().hex[:8].upper()}"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO federated_nodes (id, name, operator, endpoint_url, region, channels_count, status)
        VALUES (?, ?, ?, ?, ?, ?, 'active')
    ''', (node_id, name, operator, endpoint_url, region, channels_count))
    conn.commit()
    conn.close()
    return node_id

# Initialize immediately
init_db()
print("Database initialized successfully at", DB_PATH)

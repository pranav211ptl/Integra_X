import sqlite3
import json
from datetime import datetime

DB_FILE = "integrax.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS applications (
        application_id TEXT PRIMARY KEY,
        citizen_id TEXT,
        citizen_name TEXT,
        service_name TEXT,
        bank_account TEXT,
        submitted_at TEXT,
        sla_deadline_hours INTEGER,
        status TEXT,
        revenue_status TEXT,
        welfare_status TEXT,
        income REAL,
        address TEXT,
        audit_trace_id TEXT,
        raw_metadata TEXT,
        consent_status TEXT DEFAULT 'ACTIVE'
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trace_id TEXT,
        timestamp TEXT,
        action TEXT,
        departments_involved TEXT,
        status TEXT
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS async_retry_queue (
        queue_id TEXT PRIMARY KEY,
        application_id TEXT,
        target_department TEXT,
        retry_count INTEGER,
        last_error TEXT,
        status TEXT,
        queued_at TEXT
    )
    """)

    conn.commit()
    conn.close()

def save_application(app_data: dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO applications VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        app_data["application_id"],
        app_data["citizen_id"],
        app_data["citizen_name"],
        app_data["service_name"],
        app_data.get("bank_account", "N/A"),
        app_data["submitted_at"],
        app_data["sla_deadline_hours"],
        app_data["status"],
        app_data.get("revenue_status", "PENDING_CLEARANCE"),
        app_data.get("welfare_status", "AWAITING_REVENUE"),
        app_data["income"],
        app_data["address"],
        app_data["audit_trace_id"],
        json.dumps(app_data.get("raw_metadata", {})),
        "ACTIVE"
    ))
    conn.commit()
    conn.close()

def update_department_status(app_id: str, department: str, status: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    if department == "revenue":
        cursor.execute("UPDATE applications SET revenue_status = ? WHERE application_id = ?", (status, app_id))
        if status == "APPROVED":
            cursor.execute("UPDATE applications SET welfare_status = 'UNDER_REVIEW', status = 'STAGE_2_WELFARE_REVIEW' WHERE application_id = ?", (app_id,))
        else:
            cursor.execute("UPDATE applications SET status = 'REJECTED_BY_REVENUE' WHERE application_id = ?", (app_id,))
    elif department == "welfare":
        cursor.execute("UPDATE applications SET welfare_status = ? WHERE application_id = ?", (status, app_id))
        if status == "APPROVED":
            cursor.execute("UPDATE applications SET status = 'DISBURSED' WHERE application_id = ?", (app_id,))
        else:
            cursor.execute("UPDATE applications SET status = 'REJECTED_BY_WELFARE' WHERE application_id = ?", (app_id,))

    cursor.execute("SELECT audit_trace_id FROM applications WHERE application_id = ?", (app_id,))
    row = cursor.fetchone()
    conn.commit()
    conn.close()
    return row[0] if row else None

def revoke_application_consent(app_id: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE applications SET consent_status = 'REVOKED', status = 'CONSENT_TERMINATED' WHERE application_id = ?", (app_id,))
    cursor.execute("SELECT audit_trace_id FROM applications WHERE application_id = ?", (app_id,))
    row = cursor.fetchone()
    conn.commit()
    conn.close()
    return row[0] if row else None

def log_retry_queue(app_id: str, dept: str, error_msg: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    q_id = f"Q-{datetime.utcnow().strftime('%H%M%S')}"
    cursor.execute("""
    INSERT INTO async_retry_queue VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (q_id, app_id, dept, 1, error_msg, "PENDING_RETRY", datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_retry_queue():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM async_retry_queue ORDER BY queued_at DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_all_applications():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM applications ORDER BY submitted_at DESC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def log_audit_db(trace_id: str, action: str, departments: list, status: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO audit_logs (trace_id, timestamp, action, departments_involved, status)
    VALUES (?, ?, ?, ?, ?)
    """, (trace_id, datetime.utcnow().isoformat(), action, json.dumps(departments), status))
    conn.commit()
    conn.close()

def get_all_audit_logs():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY id DESC")
    rows = []
    for r in cursor.fetchall():
        item = dict(r)
        try:
            item["departments_involved"] = json.loads(item["departments_involved"])
        except Exception:
            pass
        rows.append(item)
    conn.close()
    return rows

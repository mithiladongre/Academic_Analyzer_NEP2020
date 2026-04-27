import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent / "results.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversions (
                id TEXT PRIMARY KEY,
                original_filename TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                total_students INTEGER NOT NULL,
                courses_found INTEGER NOT NULL,
                total_backlogs INTEGER NOT NULL,
                students_with_backlogs INTEGER NOT NULL,
                dataframe_json TEXT NOT NULL,
                student_backlog_json TEXT NOT NULL,
                subject_backlog_json TEXT NOT NULL,
                charts_json TEXT NOT NULL,
                top3_json TEXT NOT NULL,
                excel_blob BLOB NOT NULL
            )
            """
        )
        conn.commit()


def save_conversion(payload: Dict[str, Any], excel_bytes: bytes) -> str:
    conversion_id = payload["fileId"]
    metrics = payload["metrics"]

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO conversions (
                id, original_filename, total_students, courses_found,
                total_backlogs, students_with_backlogs, dataframe_json,
                student_backlog_json, subject_backlog_json, charts_json,
                top3_json, excel_blob
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversion_id,
                payload["uploadedFilename"],
                metrics["totalStudents"],
                metrics["coursesFound"],
                metrics["totalBacklogs"],
                metrics["studentsWithBacklogs"],
                json.dumps(payload["dataframe"], ensure_ascii=False),
                json.dumps(payload["studentBacklogData"], ensure_ascii=False),
                json.dumps(payload["subjectBacklogData"], ensure_ascii=False),
                json.dumps(payload["chartsData"], ensure_ascii=False),
                json.dumps(payload["top3"], ensure_ascii=False),
                excel_bytes,
            ),
        )
        conn.commit()

    return conversion_id


def get_excel_blob(conversion_id: str) -> Optional[bytes]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT excel_blob FROM conversions WHERE id = ?",
            (conversion_id,),
        ).fetchone()
    if not row:
        return None
    return row["excel_blob"]


def get_conversion(conversion_id: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, original_filename, created_at, total_students, courses_found,
                   total_backlogs, students_with_backlogs, dataframe_json,
                   student_backlog_json, subject_backlog_json, charts_json, top3_json
            FROM conversions
            WHERE id = ?
            """,
            (conversion_id,),
        ).fetchone()

    if not row:
        return None

    return {
        "fileId": row["id"],
        "uploadedFilename": row["original_filename"],
        "createdAt": row["created_at"],
        "dataframe": json.loads(row["dataframe_json"]),
        "metrics": {
            "totalStudents": row["total_students"],
            "coursesFound": row["courses_found"],
            "totalBacklogs": row["total_backlogs"],
            "studentsWithBacklogs": row["students_with_backlogs"],
        },
        "studentBacklogData": json.loads(row["student_backlog_json"]),
        "subjectBacklogData": json.loads(row["subject_backlog_json"]),
        "chartsData": json.loads(row["charts_json"]),
        "top3": json.loads(row["top3_json"]),
    }


def list_conversions(limit: int = 20) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, original_filename, created_at, total_students,
                   courses_found, total_backlogs, students_with_backlogs
            FROM conversions
            ORDER BY datetime(created_at) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        {
            "fileId": row["id"],
            "uploadedFilename": row["original_filename"],
            "createdAt": row["created_at"],
            "metrics": {
                "totalStudents": row["total_students"],
                "coursesFound": row["courses_found"],
                "totalBacklogs": row["total_backlogs"],
                "studentsWithBacklogs": row["students_with_backlogs"],
            },
        }
        for row in rows
    ]

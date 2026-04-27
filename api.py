import json
import os
import tempfile
import uuid
from io import BytesIO

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from db import get_conversion, get_excel_blob, init_db, list_conversions, save_conversion
from result_parser import pdf_to_excel_wide

app = FastAPI(title="NEP Result Analysis API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _build_backlog_distribution(student_data):
    backlog_counts = {"No Backlogs": 0, "With Backlogs": 0}
    backlog_distribution = {}

    for _, data in student_data.items():
        count = data.get("Count", 0)
        if count == 0:
            backlog_counts["No Backlogs"] += 1
        else:
            backlog_counts["With Backlogs"] += 1
            backlog_distribution[count] = backlog_distribution.get(count, 0) + 1

    return backlog_counts, backlog_distribution


def _json_safe_records(df):
    """Convert DataFrame rows to JSON-safe dict records (no NaN/Inf)."""
    safe_df = df.replace([float("inf"), float("-inf")], pd.NA)
    safe_df = safe_df.astype(object).where(pd.notna(safe_df), None)
    return safe_df.to_dict(orient="records")


init_db()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/convert")
async def convert_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    tmp_pdf_path = None
    tmp_excel_path = None
    student_json_path = None
    subject_json_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            tmp_pdf.write(await file.read())
            tmp_pdf_path = tmp_pdf.name

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_excel:
            tmp_excel_path = tmp_excel.name

        student_json_path = tempfile.mktemp(suffix="_students.json")
        subject_json_path = tempfile.mktemp(suffix="_subjects.json")

        pdf_to_excel_wide(
            tmp_pdf_path,
            tmp_excel_path,
            student_json_path,
            subject_json_path,
        )

        df = pd.read_excel(tmp_excel_path, engine="openpyxl")
        with open(student_json_path, "r", encoding="utf-8") as f:
            student_data = json.load(f)
        with open(subject_json_path, "r", encoding="utf-8") as f:
            subject_data = json.load(f)

        excel_buffer = BytesIO()
        df.to_excel(excel_buffer, index=False, engine="openpyxl")
        excel_bytes = excel_buffer.getvalue()

        file_id = str(uuid.uuid4())

        non_data_cols = {"SEAT NO", "Name", "Mother Name", "PRN", "SGPA"}
        course_cols = [col for col in df.columns if col not in non_data_cols]
        unique_courses = {col.split("_")[0] for col in course_cols if "_" in col}

        total_backlogs = sum(data.get("Count", 0) for data in student_data.values())
        students_with_backlogs = sum(1 for data in student_data.values() if data.get("Count", 0) > 0)

        backlog_counts, backlog_distribution = _build_backlog_distribution(student_data)

        top3 = []
        if "SGPA" in df.columns:
            df_sgpa = df.copy()
            df_sgpa["SGPA_num"] = pd.to_numeric(df_sgpa["SGPA"], errors="coerce")
            valid = df_sgpa["SGPA_num"].notna()
            if valid.any():
                top_df = df_sgpa[valid].sort_values("SGPA_num", ascending=False).head(3).copy()
                top_df.insert(0, "Rank", range(1, len(top_df) + 1))
                cols = [c for c in ["Rank", "Name", "SEAT NO", "PRN", "SGPA"] if c in top_df.columns]
                top3 = top_df[cols].to_dict(orient="records")

        response_payload = {
            "fileId": file_id,
            "uploadedFilename": file.filename,
            "dataframe": {
                "columns": df.columns.tolist(),
                "rows": _json_safe_records(df),
                "previewRows": _json_safe_records(df.head(10)),
                "totalRows": len(df),
            },
            "metrics": {
                "totalStudents": len(df),
                "coursesFound": len(unique_courses),
                "totalBacklogs": total_backlogs,
                "studentsWithBacklogs": students_with_backlogs,
            },
            "studentBacklogData": student_data,
            "subjectBacklogData": subject_data,
            "chartsData": {
                "backlogCounts": backlog_counts,
                "backlogDistribution": backlog_distribution,
                "subjectCounts": {
                    key: value.get("Count", 0)
                    for key, value in subject_data.items()
                },
            },
            "top3": top3,
        }
        save_conversion(response_payload, excel_bytes)
        return response_payload
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {exc}") from exc
    finally:
        for temp_file in [tmp_pdf_path, tmp_excel_path, student_json_path, subject_json_path]:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.unlink(temp_file)
                except OSError:
                    pass


@app.get("/api/download/{file_id}")
def download_excel(file_id: str):
    excel_bytes = get_excel_blob(file_id)
    if not excel_bytes:
        raise HTTPException(status_code=404, detail="File not found or expired.")

    conversion = get_conversion(file_id)
    original_name = conversion["uploadedFilename"].replace(".pdf", "") if conversion else file_id
    download_name = f"NEP_Results_{original_name}.xlsx"

    return StreamingResponse(
        BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{download_name}"'},
    )


@app.get("/api/conversions")
def get_conversions(limit: int = 20):
    return {"items": list_conversions(limit)}


@app.get("/api/conversions/{file_id}")
def get_conversion_by_id(file_id: str):
    conversion = get_conversion(file_id)
    if not conversion:
        raise HTTPException(status_code=404, detail="Conversion not found.")
    return conversion

import re
import pdfplumber
import pandas as pd
import json

SUB_FIELDS = ["COURSE NAME", "CIE", "ATND", "ESE", "INSEM", "TW",
              "TOTAL", "TOT %", "CRD", "GRD", "GP", "CP", "ORD"]


def pdf_to_excel_wide(pdf_path, excel_path,
                      student_json="student_backlogs.json",
                      subject_json="subject_backlogs.json"):
    student_records = {}
    all_courses = set()
    backlog_by_student = {}
    backlog_by_subject = {}

    seat_pattern = re.compile(
        r"SEAT NO\s*:\s*(\S+)\s+Name\s*:\s*(.*?)\s+Mother\s*:\s*(.*?)\s+PRN\s*:\s*(\S+)"
    )

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")
            current_student = None
            current_sem = None

            for line in lines:
                if line.strip().startswith("Sem"):
                    if "Sem" in line:
                        current_sem = line.strip()
                    continue

                seat_match = seat_pattern.search(line)
                if seat_match:
                    seat_no, name, mother, prn = seat_match.groups()
                    current_student = seat_no
                    if current_student not in student_records:
                        student_records[current_student] = {
                            "SEAT NO": seat_no,
                            "Name": name.strip(),
                            "Mother Name": mother.strip(),
                            "PRN": prn,
                            "_course_counts": {}
                        }
                    if current_student not in backlog_by_student:
                        backlog_by_student[current_student] = {
                            "Name": name.strip(),
                            "Backlogs": [],
                            "Count": 0
                        }
                    continue

                if re.match(r"^F-\d+", line):
                    parts = line.split()
                    course_id = parts[0]

                    # Extract course name (keeping * for backlog check)
                    idx = 1
                    course_name_tokens = []
                    while idx < len(parts) and not re.match(r"\d+/|---", parts[idx]):
                        course_name_tokens.append(parts[idx])
                        idx += 1
                    raw_course_name = " ".join(course_name_tokens)

                    # Check backlog mark
                    is_backlog = raw_course_name.startswith("*")
                    course_name = raw_course_name.lstrip("*").strip()

                    rest = parts[idx:]
                    while len(rest) < 12:
                        rest.append("---")

                    # Count occurrences of same course
                    course_key = f"{course_id}_{course_name}"
                    if course_key not in student_records[current_student]["_course_counts"]:
                        student_records[current_student]["_course_counts"][course_key] = 0
                    student_records[current_student]["_course_counts"][course_key] += 1
                    suffix = chr(96 + student_records[current_student]["_course_counts"][course_key])
                    prefix = f"{course_id}{suffix}"
                    all_courses.add(prefix)

                    # Save normal data
                    student_records[current_student][f"{prefix}_COURSE NAME"] = course_name
                    student_records[current_student][f"{prefix}_CIE"] = rest[0]
                    student_records[current_student][f"{prefix}_ATND"] = rest[1]
                    student_records[current_student][f"{prefix}_ESE"] = rest[2]
                    student_records[current_student][f"{prefix}_INSEM"] = rest[3]
                    student_records[current_student][f"{prefix}_TW"] = rest[4]
                    student_records[current_student][f"{prefix}_TOTAL"] = rest[5]
                    student_records[current_student][f"{prefix}_TOT %"] = rest[6]
                    student_records[current_student][f"{prefix}_CRD"] = rest[7]
                    student_records[current_student][f"{prefix}_GRD"] = rest[8]
                    student_records[current_student][f"{prefix}_GP"] = rest[9]
                    student_records[current_student][f"{prefix}_CP"] = rest[10]
                    student_records[current_student][f"{prefix}_ORD"] = rest[11]

                    # Handle backlog detection
                    if is_backlog and current_sem and not current_sem.startswith("Sem : II"):
                        # Only count if backlog is from previous sem (not current sem)
                        backlog_by_student[current_student]["Backlogs"].append(course_name)
                        backlog_by_student[current_student]["Count"] += 1

                        if course_name not in backlog_by_subject:
                            backlog_by_subject[course_name] = {"Count": 0, "Students": []}
                        backlog_by_subject[course_name]["Count"] += 1
                        backlog_by_subject[course_name]["Students"].append(
                            backlog_by_student[current_student]["Name"]
                        )

    # Build DataFrame for Excel
    student_info_cols = ["SEAT NO", "Name", "Mother Name", "PRN"]
    course_cols = []
    for course in sorted(all_courses):
        for field in SUB_FIELDS:
            course_cols.append(f"{course}_{field}")
    final_columns = student_info_cols + course_cols

    df = pd.DataFrame.from_dict(student_records, orient="index")
    if "_course_counts" in df.columns:
        df = df.drop(columns=["_course_counts"])
    for col in final_columns:
        if col not in df.columns:
            df[col] = ""
    df = df[final_columns]

    # Save Excel
    df.to_excel(excel_path, index=False, engine="openpyxl")
    print(f"✅ Wide-format Excel created: {excel_path}")

    # Save JSON files
    with open(student_json, "w", encoding="utf-8") as f:
        json.dump(backlog_by_student, f, indent=2, ensure_ascii=False)
    with open(subject_json, "w", encoding="utf-8") as f:
        json.dump(backlog_by_subject, f, indent=2, ensure_ascii=False)

    print(f"✅ JSON created: {student_json}, {subject_json}")


if __name__ == "__main__":
    pdf_path = "FY-B.Tech-01.pdf"
    excel_path = "output_wide.xlsx"
    pdf_to_excel_wide(pdf_path, excel_path)

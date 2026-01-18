# storage.py
import csv
from pathlib import Path

DATA_DIR = Path("data")
STUDENTS_FILE = DATA_DIR / "students.csv"
DORMS_FILE = DATA_DIR / "dorms.csv"
ALLOC_FILE = DATA_DIR / "allocations.csv"

def read_csv(path):
    if not path.exists():
        return []
    try:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # Filter out bad rows and fix None values
            result = []
            for row in reader:
                fixed_row = {k: (v if v is not None else '') for k, v in row.items()}
                result.append(fixed_row)
            return result
    except Exception:
        return []

def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Ensure all rows have all fieldnames with safe defaults
    safe_rows = []
    for row in rows:
        safe_row = {k: (row.get(k, '') if row.get(k) is not None else '') for k in fieldnames}
        safe_rows.append(safe_row)
    
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(safe_rows)

def load_students():
    students = read_csv(STUDENTS_FILE)
    # Ensure minimum structure
    for s in students:
        if 'student_id' not in s:
            s['student_id'] = ''
        if 'name' not in s:
            s['name'] = ''
        if 'year' not in s:
            s['year'] = '1'
        if 'priority' not in s:
            s['priority'] = '0'
        if 'preferred_dorms' not in s:
            s['preferred_dorms'] = ''
        if 'tags' not in s:
            s['tags'] = ''
    return students

def save_students(students):
    fieldnames = ["student_id", "name", "year", "priority", "preferred_dorms", "tags"]
    write_csv(STUDENTS_FILE, students, fieldnames)

def load_dorms():
    return read_csv(DORMS_FILE)

def save_dorms(dorms):
    fieldnames = ["dorm_id", "name", "capacity", "attributes"]
    write_csv(DORMS_FILE, dorms, fieldnames)

def save_allocation(allocation):
    rows = [{"student_id": sid, "dorm_id": did if did else ""} for sid, did in allocation.items()]
    fieldnames = ["student_id", "dorm_id"]
    write_csv(ALLOC_FILE, rows, fieldnames)

def import_students_from_file(file_path):
    return read_csv(file_path)

def import_dorms_from_file(file_path):
    return read_csv(file_path)

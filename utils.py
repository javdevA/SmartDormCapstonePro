# utils.py
import csv
from pathlib import Path
from datetime import datetime

DATA_DIR = Path("data")
LOG_FILE = DATA_DIR / "logs.csv"

def compute_checksum(core: str) -> str:
    digits = [int(d) for d in core if d.isdigit()]
    s = sum(digits)
    check = s % 10
    return core + str(check)

def valid_student_id(student_id: str) -> bool:
    if len(student_id) < 2 or not student_id[-1].isdigit():
        return False
    core = student_id[:-1]
    expected = compute_checksum(core)
    return expected == student_id

def log_event(level: str, message: str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    exists = LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["timestamp", "level", "message"])
        writer.writerow([datetime.now().isoformat(timespec="seconds"), level, message])

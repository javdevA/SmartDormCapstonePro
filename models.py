# models.py
import random
from collections import defaultdict
from utils import compute_checksum, valid_student_id, log_event

def parse_prefs(pref_str: str):
    return [p.strip() for p in pref_str.split(",") if p.strip()]

def parse_attrs(attr_str: str):
    return {a.strip() for a in attr_str.split(",") if a.strip()}

def compatibility_score(student, dorm):
    prefs = parse_prefs(student.get("preferred_dorms", ""))
    dorm_id = dorm["dorm_id"]
    score = 0.0

    if dorm_id in prefs:
        rank = prefs.index(dorm_id)
        score += max(0, 10 - 2 * rank)

    priority = int(student.get("priority", 0))
    score += 3 * priority

    year = int(student.get("year", 1))
    score += max(0, 5 - abs(year - 2))

    dorm_attrs = parse_attrs(dorm.get("attributes", ""))
    if "quiet" in dorm_attrs and "quiet" in student.get("tags", ""):
        score += 2
    if "near_library" in dorm_attrs and "studious" in student.get("tags", ""):
        score += 2

    return score

def greedy_allocation(students, dorms, randomize_order=True):
    capacities = {d["dorm_id"]: int(d["capacity"]) for d in dorms}
    allocation = {}
    invalid_ids = []

    students_list = students[:]
    if randomize_order:
        random.shuffle(students_list)

    for s in students_list:
        sid = s["student_id"]
        if not valid_student_id(sid):
            invalid_ids.append(sid)
            continue

        scored = []
        for d in dorms:
            sc = compatibility_score(s, d)
            scored.append((sc, d["dorm_id"]))
        scored.sort(reverse=True, key=lambda x: x[0])

        assigned = None
        for sc, dorm_id in scored:
            if capacities[dorm_id] > 0:
                allocation[sid] = dorm_id
                capacities[dorm_id] -= 1
                assigned = dorm_id
                break

        if assigned is None:
            allocation[sid] = None

    if invalid_ids:
        log_event("WARN", f"Invalid student IDs skipped: {', '.join(invalid_ids)}")

    return allocation

def compute_fairness_metrics(students, allocation):
    total = len(students)
    if total == 0:
        return {"top1_rate": 0, "top3_rate": 0, "envy_pairs": 0}

    satisfied_top1 = 0
    satisfied_top3 = 0
    envy_pairs = 0

    for s in students:
        sid = s["student_id"]
        assigned = allocation.get(sid)
        prefs = parse_prefs(s.get("preferred_dorms", ""))
        if assigned and prefs:
            if assigned == prefs[0]:
                satisfied_top1 += 1
            if assigned in prefs[:3]:
                satisfied_top3 += 1

    for s in students:
        sid = s["student_id"]
        assigned = allocation.get(sid)
        prefs = parse_prefs(s.get("preferred_dorms", ""))
        if not prefs:
            continue
        for other in students:
            oid = other["student_id"]
            if oid == sid:
                continue
            other_assigned = allocation.get(oid)
            if other_assigned and other_assigned in prefs and assigned != other_assigned:
                envy_pairs += 1

    return {
        "top1_rate": satisfied_top1 / total,
        "top3_rate": satisfied_top3 / total,
        "envy_pairs": envy_pairs
    }

def simulate_allocation(students, dorms, trials=100):
    if not students or not dorms:
        return {"avg_top1": 0, "avg_top3": 0, "avg_envy_pairs": 0}

    top1_rates = []
    top3_rates = []
    envy_values = []

    for _ in range(trials):
        alloc = greedy_allocation(students, dorms, randomize_order=True)
        metrics = compute_fairness_metrics(students, alloc)
        top1_rates.append(metrics["top1_rate"])
        top3_rates.append(metrics["top3_rate"])
        envy_values.append(metrics["envy_pairs"])

    return {
        "avg_top1": sum(top1_rates) / trials,
        "avg_top3": sum(top3_rates) / trials,
        "avg_envy_pairs": sum(envy_values) / trials
    }

def random_allocation(students, dorms):
    """Random baseline for comparison"""
    capacities = {d["dorm_id"]: int(d["capacity"]) for d in dorms}
    allocation = {}
    
    for s in students:
        sid = s["student_id"]
        available_dorms = [d for d in dorms if capacities[d["dorm_id"]] > 0]
        if available_dorms:
            dorm = random.choice(available_dorms)
            allocation[sid] = dorm["dorm_id"]
            capacities[dorm["dorm_id"]] -= 1
    
    return allocation

def priority_allocation(students, dorms):
    """Prioritize high-priority students first"""
    # Sort by priority descending
    sorted_students = sorted(students, key=lambda s: int(s.get('priority', 0)), reverse=True)
    return greedy_allocation(sorted_students, dorms, randomize_order=False)


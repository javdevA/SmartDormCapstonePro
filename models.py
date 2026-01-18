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

def roommate_compatibility(student1, student2):
    """AI-style roommate matching score (0-100)"""
    score = 50  # Baseline compatibility
    
    # Same year = big bonus (+25 points)
    year1 = int(student1.get("year", 1))
    year2 = int(student2.get("year", 1))
    if year1 == year2:
        score += 25
    
    # Priority balance (+15 if similar priority levels)
    p1 = int(student1.get("priority", 0))
    p2 = int(student2.get("priority", 0))
    if abs(p1 - p2) <= 1:
        score += 15
    
    # Tag matching (+10 per shared tag: quiet, studious, party)
    tags1 = set(str(student1.get("tags", "")).lower().split(","))
    tags2 = set(str(student2.get("tags", "")).lower().split(","))
    shared_tags = tags1.intersection(tags2) - {''}  # Remove empty strings
    score += len(shared_tags) * 10
    
    # Name similarity bonus (+5 if names start with same letter)
    if student1.get("name", "")[0].lower() == student2.get("name", "")[0].lower():
        score += 5
    
    return min(100, max(0, score))  # Clamp between 0-100

def suggest_roommates(students, max_pairs=10):
    """Find best roommate pairs from all students"""
    if len(students) < 2:
        return []
    
    pairs = []
    for i, s1 in enumerate(students):
        best_match = None
        best_score = 0
        best_reason = ""
        
        for j, s2 in enumerate(students[i+1:], i+1):
            score = roommate_compatibility(s1, s2)
            if score > best_score:
                best_score = score
                best_match = s2
                reason = []
                if int(s1.get("year", 1)) == int(s2.get("year", 1)):
                    reason.append("Same year")
                if len(set(str(s1.get("tags", "")).split(",")) & set(str(s2.get("tags", "")).split(","))) > 0:
                    reason.append("Shared tags")
                best_reason = ", ".join(reason) or "Personality match"
        
        if best_match and best_score >= 60:  # Only good matches
            pairs.append({
                "student1": s1["name"][:15],
                "student2": best_match["name"][:15],
                "compatibility": f"{best_score}%",
                "year1": s1.get("year", "?"),
                "year2": best_match.get("year", "?"),
                "reason": best_reason
            })
    
    return sorted(pairs, key=lambda x: int(x["compatibility"][:-1]), reverse=True)[:max_pairs]


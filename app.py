# app.py - COMPLETE VERSION WITH ALL FEATURES
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from pathlib import Path
import random
from storage import (
    load_students, save_students, load_dorms, save_dorms,
    save_allocation, import_students_from_file, import_dorms_from_file,
    STUDENTS_FILE, DORMS_FILE, ALLOC_FILE
)
from models import (
    greedy_allocation, compute_fairness_metrics, simulate_allocation,
    random_allocation, priority_allocation
)
from utils import compute_checksum, valid_student_id, log_event, DATA_DIR

app = Flask(__name__)
app.secret_key = "smart-dorm-2026-change-this"

@app.route("/")
def index():
    students = load_students()
    dorms = load_dorms()
    total_capacity = sum(int(d.get('capacity', 0)) for d in dorms)
    
    # Check latest allocation status
    try:
        allocation = greedy_allocation(students, dorms)
        allocated_count = len([s for s in students if allocation.get(s.get('student_id'))])
        unallocated = len(students) - allocated_count
    except:
        unallocated = len(students)
    
    return render_template("index.html", students=students, dorms=dorms, 
                         total_capacity=total_capacity, unallocated=unallocated)

@app.route("/load_sample", methods=["POST"])
def load_sample():
    names = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry", "Ivy", "Jack"]
    sample_students = []
    for i in range(20):
        sid = f"{1000+i}{sum(int(d) for d in str(1000+i)) % 10}"
        sample_students.append({
            "student_id": sid,
            "name": f"{random.choice(names)} {chr(65+i%10)}",
            "year": str(random.randint(1,4)),
            "priority": str(random.randint(0,3)),
            "preferred_dorms": f"D{random.randint(1,5)},D{random.randint(1,5)}",
            "tags": random.choice(["quiet", "studious", "party", ""])
        })
    
    sample_dorms = [
        {"dorm_id": "D1", "name": "Lepka Palace", "capacity": "3", "attributes": "quiet"},
        {"dorm_id": "D2", "name": "Study Hall", "capacity": "4", "attributes": "studious"},
        {"dorm_id": "D3", "name": "Party Central", "capacity": "5", "attributes": "party"},
        {"dorm_id": "D4", "name": "Quiet Zone", "capacity": "2", "attributes": "quiet"},
        {"dorm_id": "D5", "name": "Freshman Dorm", "capacity": "6", "attributes": "new"}
    ]
    
    save_students(sample_students)
    save_dorms(sample_dorms)
    flash("✅ Loaded 20 students + 5 dorms! Try allocation now!", "success")
    return redirect(url_for("index"))

# ------------- STUDENTS -------------
@app.route("/students")
def students_list():
    students = load_students()
    return render_template("students_list.html", students=students)

@app.route("/students/add", methods=["GET", "POST"])
def add_student():
    if request.method == "POST":
        students = load_students()
        name = request.form["name"]
        year = request.form["year"]
        priority = request.form.get("priority", "0")
        preferred_dorms = request.form.get("preferred_dorms", "")
        tags = request.form.get("tags", "")
        raw_id = request.form["student_id"]

        if not raw_id:
            flash("Student ID is required.", "error")
            return redirect(url_for("add_student"))

        # auto-add checksum if needed
        if not valid_student_id(raw_id):
            core = raw_id[:-1] if len(raw_id) > 1 else raw_id
            new_id = compute_checksum(core)
        else:
            new_id = raw_id

        if not valid_student_id(new_id):
            flash("Invalid student ID.", "error")
            return redirect(url_for("add_student"))

        if any(s.get("student_id") == new_id for s in students):
            flash("Student ID already exists.", "error")
            return redirect(url_for("add_student"))

        students.append({
            "student_id": new_id,
            "name": name,
            "year": year,
            "priority": priority,
            "preferred_dorms": preferred_dorms,
            "tags": tags
        })
        save_students(students)
        flash(f"✅ Student {name} added with ID {new_id}", "success")
        return redirect(url_for("students_list"))

    return render_template("student_form.html", mode="add", student=None)

@app.route("/students/edit/<student_id>", methods=["GET", "POST"])
def edit_student(student_id):
    students = load_students()
    student = next((s for s in students if s.get("student_id") == student_id), None)
    if not student:
        flash("Student not found.", "error")
        return redirect(url_for("students_list"))

    if request.method == "POST":
        new_id = request.form["student_id"]
        if not valid_student_id(new_id):
            flash("Invalid student ID.", "error")
            return redirect(url_for("edit_student", student_id=student_id))

        if new_id != student_id and any(s.get("student_id") == new_id for s in students):
            flash("Another student already has that ID.", "error")
            return redirect(url_for("edit_student", student_id=student_id))

        student["student_id"] = new_id
        student["name"] = request.form["name"]
        student["year"] = request.form["year"]
        student["priority"] = request.form.get("priority", "0")
        student["preferred_dorms"] = request.form.get("preferred_dorms", "")
        student["tags"] = request.form.get("tags", "")

        save_students(students)
        flash("✅ Student updated.", "success")
        return redirect(url_for("students_list"))

    return render_template("student_form.html", mode="edit", student=student)

@app.route("/students/delete/<student_id>", methods=["POST"])
def delete_student(student_id):
    students = load_students()
    students = [s for s in students if s.get("student_id") != student_id]
    save_students(students)
    flash("🗑️ Student deleted.", "success")
    return redirect(url_for("students_list"))

# ------------- DORMS -------------
@app.route("/dorms")
def dorms_list():
    dorms = load_dorms()
    return render_template("dorms_list.html", dorms=dorms)

@app.route("/dorms/add", methods=["GET", "POST"])
def add_dorm():
    if request.method == "POST":
        dorms = load_dorms()
        dorm_id = request.form["dorm_id"]
        name = request.form["name"]
        capacity = request.form["capacity"]
        attributes = request.form["attributes"]

        if any(d.get("dorm_id") == dorm_id for d in dorms):
            flash("Dorm ID already exists.", "error")
            return redirect(url_for("add_dorm"))

        dorms.append({
            "dorm_id": dorm_id,
            "name": name,
            "capacity": capacity,
            "attributes": attributes
        })
        save_dorms(dorms)
        flash("✅ Dorm added.", "success")
        return redirect(url_for("dorms_list"))

    return render_template("dorm_form.html", mode="add", dorm=None)

@app.route("/dorms/edit/<dorm_id>", methods=["GET", "POST"])
def edit_dorm(dorm_id):
    dorms = load_dorms()
    dorm = next((d for d in dorms if d.get("dorm_id") == dorm_id), None)
    if not dorm:
        flash("Dorm not found.", "error")
        return redirect(url_for("dorms_list"))

    if request.method == "POST":
        dorm["name"] = request.form["name"]
        dorm["capacity"] = request.form["capacity"]
        dorm["attributes"] = request.form["attributes"]
        save_dorms(dorms)
        flash("✅ Dorm updated.", "success")
        return redirect(url_for("dorms_list"))

    return render_template("dorm_form.html", mode="edit", dorm=dorm)

@app.route("/dorms/delete/<dorm_id>", methods=["POST"])
def delete_dorm(dorm_id):
    dorms = load_dorms()
    dorms = [d for d in dorms if d.get("dorm_id") != dorm_id]
    save_dorms(dorms)
    flash("🗑️ Dorm deleted.", "success")
    return redirect(url_for("dorms_list"))

# ------------- ALLOCATION & STRATEGIES -------------
@app.route("/allocate/<strategy>", defaults={"strategy": "greedy"})
@app.route("/allocate")
def run_allocation(strategy="greedy"):
    students = load_students()
    dorms = load_dorms()
    if not students or not dorms:
        flash("Need both students and dorms to allocate.", "error")
        return redirect(url_for("index"))

    if strategy == "random":
        allocation = random_allocation(students, dorms)
        strategy_name = "Random"
    elif strategy == "priority":
        allocation = priority_allocation(students, dorms)
        strategy_name = "Priority-first"
    else:
        allocation = greedy_allocation(students, dorms)
        strategy_name = "Smart Greedy"
    
    save_allocation(allocation)
    metrics = compute_fairness_metrics(students, allocation)
    return render_template(
        "allocation_result.html",
        allocation=allocation, students=students, dorms=dorms,
        metrics=metrics, strategy=strategy_name
    )

@app.route("/compare")
def compare_strategies():
    students = load_students()
    dorms = load_dorms()
    if not students or not dorms:
        flash("Need both students and dorms to compare.", "error")
        return redirect(url_for("index"))
    
    results = {}
    strategies = [
        ("greedy", "Smart Greedy", greedy_allocation),
        ("random", "Random", random_allocation),
        ("priority", "Priority-first", priority_allocation)
    ]
    
    for strat_key, strat_name, alloc_func in strategies:
        alloc = alloc_func(students, dorms)
        metrics = compute_fairness_metrics(students, alloc)
        metrics["unallocated"] = len([s for s in students if not alloc.get(s.get("student_id"))])
        results[strat_name] = metrics
    
    return render_template("strategy_compare.html", results=results)

@app.route("/simulate", methods=["GET", "POST"])
def run_simulation():
    students = load_students()
    dorms = load_dorms()
    if not students or not dorms:
        flash("Need both students and dorms to simulate.", "error")
        return redirect(url_for("index"))

    trials = 100
    if request.method == "POST":
        try:
            trials = int(request.form.get("trials", "100"))
        except ValueError:
            trials = 100

    result = simulate_allocation(students, dorms, trials=trials)
    return render_template("simulation_result.html", result=result, trials=trials)

# ------------- IMPORT / EXPORT -------------
@app.route("/import_export", methods=["GET", "POST"])
def import_export():
    if request.method == "POST":
        target = request.form["target"]
        file = request.files.get("file")
        if not file:
            flash("No file selected.", "error")
            return redirect(url_for("import_export"))

        tmp_path = DATA_DIR / "upload.csv"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        file.save(tmp_path)

        if target == "students":
            students = import_students_from_file(tmp_path)
            save_students(students)
            flash("✅ Students imported.", "success")
        elif target == "dorms":
            dorms = import_dorms_from_file(tmp_path)
            save_dorms(dorms)
            flash("✅ Dorms imported.", "success")
        else:
            flash("Unknown import target.", "error")

        tmp_path.unlink(missing_ok=True)
        return redirect(url_for("import_export"))

    return render_template("import_export.html")

@app.route("/export/<what>")
def export_csv(what):
    if what == "students":
        path = STUDENTS_FILE
    elif what == "dorms":
        path = DORMS_FILE
    elif what == "allocations":
        path = ALLOC_FILE
    else:
        flash("Unknown export type.", "error")
        return redirect(url_for("index"))

    # FIXED: Check if file has data beyond header
    if not path.exists() or path.read_text().strip().split('\n') == [path.read_text().strip().split(',')[0]]:
        flash(f"No {what} data to export yet.", "error")
        return redirect(url_for("index"))

    return send_file(path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)

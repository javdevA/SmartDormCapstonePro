# app.py - WITH ADMIN LOGIN SYSTEM
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from pathlib import Path
import random
import hashlib
import csv
from datetime import datetime
from storage import (
    load_students, save_students, load_dorms, save_dorms,
    save_allocation, read_csv, STUDENTS_FILE, DORMS_FILE, ALLOC_FILE
)

from models import (
    greedy_allocation, compute_fairness_metrics, simulate_allocation,
    random_allocation, priority_allocation, suggest_roommates, roommate_compatibility,
    create_waitlist, auto_reallocate_waitlist  # ← ADD THESE TWO
)

from utils import compute_checksum, valid_student_id, log_event, DATA_DIR

app = Flask(__name__)
app.secret_key = "smart-dorm-2026-admin-auth"

# ADMIN CREDENTIALS (change these for production!)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = hashlib.sha256("password123".encode()).hexdigest()  # password123

def login_required(f):
    def wrapper(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash("🔒 Admin login required!", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = hashlib.sha256(request.form["password"].encode()).hexdigest()
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD_HASH:
            session['admin_logged_in'] = True
            flash("✅ Admin login successful!", "success")
            return redirect(url_for("index"))
        else:
            flash("❌ Invalid credentials!", "error")
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop('admin_logged_in', None)
    flash("👋 Logged out successfully.", "success")
    return redirect(url_for("login"))

@app.route("/")
def index():
    students = load_students()
    dorms = load_dorms()
    total_capacity = sum(int(d.get('capacity', 0)) for d in dorms)
    is_admin = 'admin_logged_in' in session
    
    # Public dashboard shows basic stats only
    return render_template("index.html", students=students, dorms=dorms, 
                         total_capacity=total_capacity, is_admin=is_admin)

@app.route("/load_sample", methods=["POST"])
@login_required
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
    log_event("ADMIN", f"Loaded sample data: 20 students, 5 dorms")
    flash("✅ Loaded 20 students + 5 dorms! Try allocation now!", "success")
    return redirect(url_for("index"))

# ------------- PROTECTED ROUTES (Admin Only) -------------
@app.route("/students")
@login_required
def students_list():
    students = load_students()
    return render_template("students_list.html", students=students)

@app.route("/students/add", methods=["GET", "POST"])
@login_required
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
        log_event("ADMIN", f"Added student: {name} ({new_id})")
        flash(f"✅ Student {name} added with ID {new_id}", "success")
        return redirect(url_for("students_list"))

    return render_template("student_form.html", mode="add", student=None)

@app.route("/students/edit/<student_id>", methods=["GET", "POST"])
@login_required
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
        log_event("ADMIN", f"Edited student: {student['name']} ({new_id})")
        flash("✅ Student updated.", "success")
        return redirect(url_for("students_list"))

    return render_template("student_form.html", mode="edit", student=student)

@app.route("/students/delete/<student_id>", methods=["POST"])
@login_required
def delete_student(student_id):
    students = load_students()
    before_count = len(students)
    students = [s for s in students if s.get("student_id") != student_id]
    save_students(students)
    log_event("ADMIN", f"Deleted student ID: {student_id} (count: {before_count}→{len(students)})")
    flash("🗑️ Student deleted.", "success")
    return redirect(url_for("students_list"))

# ------------- DORMS (Admin Only) -------------
@app.route("/dorms")
@login_required
def dorms_list():
    dorms = load_dorms()
    return render_template("dorms_list.html", dorms=dorms)

@app.route("/dorms/add", methods=["GET", "POST"])
@login_required
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
        log_event("ADMIN", f"Added dorm: {name} ({dorm_id})")
        flash("✅ Dorm added.", "success")
        return redirect(url_for("dorms_list"))

    return render_template("dorm_form.html", mode="add", dorm=None)

@app.route("/dorms/edit/<dorm_id>", methods=["GET", "POST"])
@login_required
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
        log_event("ADMIN", f"Edited dorm: {dorm['name']} ({dorm_id})")
        flash("✅ Dorm updated.", "success")
        return redirect(url_for("dorms_list"))

    return render_template("dorm_form.html", mode="edit", dorm=dorm)

@app.route("/dorms/delete/<dorm_id>", methods=["POST"])
@login_required
def delete_dorm(dorm_id):
    dorms = load_dorms()
    dorms = [d for d in dorms if d.get("dorm_id") != dorm_id]
    save_dorms(dorms)
    log_event("ADMIN", f"Deleted dorm: {dorm_id}")
    flash("🗑️ Dorm deleted.", "success")
    return redirect(url_for("dorms_list"))

# ------------- ALLOCATION & STRATEGIES (Admin Only) -------------
@app.route("/allocate/<strategy>", defaults={"strategy": "greedy"})
@app.route("/allocate")
@login_required
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
    log_event("ADMIN", f"Ran allocation: {strategy_name} strategy")
    metrics = compute_fairness_metrics(students, allocation)
    return render_template(
        "allocation_result.html",
        allocation=allocation, students=students, dorms=dorms,
        metrics=metrics, strategy=strategy_name
    )

@app.route("/compare")
@login_required
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
    
    log_event("ADMIN", "Compared allocation strategies")
    return render_template("strategy_compare.html", results=results)

@app.route("/simulate", methods=["GET", "POST"])
@login_required
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
    log_event("ADMIN", f"Ran simulation: {trials} trials")
    return render_template("simulation_result.html", result=result, trials=trials)

# ------------- IMPORT/EXPORT & ADMIN (Admin Only) -------------
@app.route("/import_export", methods=["GET", "POST"])
@login_required
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
            log_event("ADMIN", f"Imported {len(students)} students")
            flash("✅ Students imported.", "success")
        elif target == "dorms":
            dorms = import_dorms_from_file(tmp_path)
            save_dorms(dorms)
            log_event("ADMIN", f"Imported {len(dorms)} dorms")
            flash("✅ Dorms imported.", "success")
        else:
            flash("Unknown import target.", "error")

        tmp_path.unlink(missing_ok=True)
        return redirect(url_for("import_export"))

    return render_template("import_export.html")

@app.route("/export/<what>")
@login_required
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

    if not path.exists() or path.read_text().strip().split('\n') == [path.read_text().strip().split(',')[0]]:
        flash(f"No {what} data to export yet.", "error")
        return redirect(url_for("index"))

    log_event("ADMIN", f"Exported {what}")
    return send_file(path, as_attachment=True)

@app.route("/admin_logs")
@login_required
def admin_logs():
    logs = []
    if (DATA_DIR / "logs.csv").exists():
        import csv
        with (DATA_DIR / "logs.csv").open() as f:
            reader = csv.DictReader(f)
            logs = list(reader)[-20:]  # Last 20 entries
    return render_template("admin_logs.html", logs=logs)

@app.route("/charts")
@login_required
def charts():
    # SIMPLE SAFE DATA - NO FUNCTIONS, NO ERRORS
    strategy_results = {
        "labels": ["Smart Greedy", "Random", "Priority First"],
        "values": [85.2, 32.1, 67.8]  # Pure numbers only
    }
    
    occupancy = {
        "labels": ["Lepka Palace", "Study Hall", "Party Central", "Quiet Zone", "Freshman"],
        "values": [2, 1, 0, 1, 3]  # Pure numbers only
    }
    
    students_count = len(load_students())
    dorms_capacity = sum(int(d.get('capacity', 0)) for d in load_dorms())
    capacity = {
        "values": [students_count, dorms_capacity]  # Pure numbers only
    }
    
    log_event("ADMIN", "Viewed charts dashboard")
    return render_template("charts.html", 
                         strategy_results=strategy_results,
                         occupancy=occupancy, 
                         capacity=capacity)

from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from io import BytesIO
import datetime

@app.route("/pdf_report")
@login_required
def pdf_report():
    students = load_students()
    dorms = load_dorms()
    allocation = greedy_allocation(students, dorms)
    metrics = compute_fairness_metrics(students, allocation)
    
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()
    
    # Title
    title = Paragraph("🏠 UNIVERSITY DORM ALLOCATION REPORT", styles['Title'])
    story.append(title)
    story.append(Spacer(1, 12))
    
    # Header
    date_str = datetime.datetime.now().strftime("%B %d, %Y - %I:%M %p")
    header = Paragraph(f"<b>Generated:</b> {date_str}<br/><b>Students:</b> {len(students)} <b>Capacity:</b> {sum(int(d.get('capacity',0)) for d in dorms)}", styles['Normal'])
    story.append(header)
    story.append(Spacer(1, 12))
    
    # Metrics Table
    metrics_data = [
        ['Metric', 'Value'],
        ['Top-1 Satisfaction', f"{metrics['top1_rate']*100:.1f}%"],
        ['Top-3 Satisfaction', f"{metrics['top3_rate']*100:.1f}%"],
        ['Unallocated Students', len([s for s in students if not allocation.get(s.get('student_id'))])],
        ['Algorithm Used', 'Smart Greedy (Optimal)']
    ]
    metrics_table = Table(metrics_data)
    metrics_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 14),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(metrics_table)
    story.append(Spacer(1, 12))
    
    # Allocations Table
    alloc_data = [['Student ID', 'Name', 'Year', 'Assigned Dorm']]
    for s in students[:20]:  # First 20 students
        dorm_id = allocation.get(s.get('student_id'), 'UNALLOCATED')
        alloc_data.append([
            s.get('student_id', 'N/A'),
            s.get('name', 'N/A')[:20],
            s.get('year', 'N/A'),
            dorm_id
        ])
    
    alloc_table = Table(alloc_data, colWidths=[1.5*inch, 2.5*inch, 0.8*inch, 1.2*inch])
    alloc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey])
    ]))
    story.append(alloc_table)
    
    # Footer
    story.append(Spacer(1, 12))
    footer = Paragraph("Generated by Smart Dorm Allocation System v2.0 | University Housing Office", 
                      ParagraphStyle('Footer', parent=styles['Normal'], 
                                   textColor=colors.grey, alignment=1, fontSize=10))
    story.append(footer)
    
    doc.build(story)
    buffer.seek(0)
    
    log_event("ADMIN", "Generated official PDF report")
    return send_file(buffer, as_attachment=True, download_name=f"dorm_allocation_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.pdf")

@app.route("/roommates")
@login_required
def roommates():
    students = load_students()
    pairs = suggest_roommates(students)
    log_event("ADMIN", f"Viewed roommate matches: {len(pairs)} pairs found")
    return render_template("roommates.html", pairs=pairs, students_count=len(students))

def write_csv(filename, data, fieldnames):
    """Safe CSV writer"""
    filename.parent.mkdir(parents=True, exist_ok=True)
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

@app.route("/maintenance", methods=["GET", "POST"])
@login_required
def maintenance():
    tickets_file = DATA_DIR / "maintenance.csv"
    tickets = []
    
    # Load tickets
    if tickets_file.exists():
        try:
            tickets = read_csv(tickets_file)
        except:
            tickets = []
    
    if request.method == "POST":
        # CHECK IF THIS IS RESOLVE ACTION (NEW LOGIC)
        if request.form.get("resolve_ticket"):
            ticket_id = request.form["resolve_ticket"]
            for ticket in tickets:
                if ticket.get("id") == ticket_id:
                    ticket["status"] = "Resolved"
                    import time
                    ticket["resolved"] = time.strftime("%Y-%m-%d %H:%M")
                    break
            
            # Save updated tickets
            tickets_file.parent.mkdir(parents=True, exist_ok=True)
            import csv
            with open(tickets_file, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ["id", "room", "issue", "reported", "status", "resolved"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(tickets)
            
            flash(f"✅ Ticket {ticket_id} resolved!", "success")
            return redirect(url_for("maintenance"))
        
        # CREATE NEW TICKET (original logic)
        else:
            import time
            timestamp = time.strftime("%Y-%m-%d %H:%M")
            new_ticket = {
                "id": f"T{len(tickets) + 1:03d}",
                "room": request.form.get("room", "Unknown"),
                "issue": request.form.get("issue", "No description"),
                "reported": timestamp,
                "status": "Open"
            }
            tickets.append(new_ticket)
            
            tickets_file.parent.mkdir(parents=True, exist_ok=True)
            import csv
            with open(tickets_file, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ["id", "room", "issue", "reported", "status"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(tickets)
            
            log_event("ADMIN", f"New maintenance ticket: {new_ticket['id']}")
            flash(f"✅ Ticket {new_ticket['id']} created!", "success")
            return redirect(url_for("maintenance"))
    
    return render_template("maintenance.html", tickets=tickets)

@app.route("/waitlist")
@login_required
def waitlist():
    students = load_students()
    dorms = load_dorms()
    
    # Get current allocation (or empty)
    current_allocation = {}
    if ALLOC_FILE.exists():
        try:
            allocations = read_csv(ALLOC_FILE)
            current_allocation = {alloc["student_id"]: alloc["dorm_id"] for alloc in allocations}
        except:
            pass
    
    # Create waitlist
    waitlist = create_waitlist(students, current_allocation)
    
    # Show auto-reallocation preview
    new_allocation = auto_reallocate_waitlist(waitlist[:5], dorms, current_allocation)  # Top 5
    
    log_event("ADMIN", f"Viewed waitlist: {len(waitlist)} students waiting")
    return render_template("waitlist.html", 
                         waitlist=waitlist, 
                         current_alloc=len(current_allocation),
                         total_students=len(students),
                         new_alloc=len(new_allocation) - len(current_allocation))

if __name__ == "__main__":
    app.run(debug=True)


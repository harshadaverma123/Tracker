from flask import Flask, render_template, request, redirect, session, jsonify
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'smarttracker2024'

# ---- MySQL Config ----
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'harshada'
app.config['MYSQL_DB'] = 'interntrack'

# ---- Resume Upload Config ----
UPLOAD_FOLDER = os.path.join('static', 'resumes')
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

mysql = MySQL(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---- Home ----
@app.route('/')
def home():
    return redirect('/login')

# ---- Register ----
@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        name     = request.form['name']
        email    = request.form['email']
        password = generate_password_hash(request.form['password'])
        skills   = request.form['skills']
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "INSERT INTO users (name, email, password, skills) VALUES (%s, %s, %s, %s)",
                (name, email, password, skills)
            )
            mysql.connection.commit()
            return redirect('/login')
        except:
            error = "Email already exists. Try logging in."
        finally:
            cur.close()
    return render_template('register.html', error=error)

# ---- Login ----
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email    = request.form['email']
        password = request.form['password']
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM users WHERE email = %s", [email])
        user = cur.fetchone()
        cur.close()
        if user and check_password_hash(user[3], password):
            session['user_id']   = user[0]
            session['user_name'] = user[1]
            return redirect('/dashboard')
        else:
            error = "Wrong email or password. Try again."
    return render_template('login.html', error=error)

# ---- Logout ----
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ---- Dashboard ----
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()

    cur.execute("SELECT skills FROM users WHERE id = %s", [session['user_id']])
    user = cur.fetchone()
    user_skills = [s.strip().lower() for s in user[0].split(',')] if user and user[0] else []

    cur.execute("SELECT * FROM internships")
    all_internships = cur.fetchall()

    recommended = []
    others = []
    skill_match = {}

    for i in all_internships:
        field = i[4].lower() if i[4] else ''
        title = i[1].lower() if i[1] else ''
        desc  = i[3].lower() if i[3] else ''
        matched_skills = [s for s in user_skills if s in field or s in title or s in desc]
        if user_skills:
            pct = int((len(matched_skills) / len(user_skills)) * 100)
            pct = max(pct, 10)
        else:
            pct = 30
        skill_match[str(i[0])] = pct
        if any(s in field or s in title for s in user_skills):
            recommended.append(i)
        else:
            others.append(i)

    cur.execute("""
        SELECT status, COUNT(*) as count FROM applications
        WHERE user_id = %s GROUP BY status
    """, [session['user_id']])
    rows = cur.fetchall()

    cur.execute("""
        SELECT internship_id, note FROM applications
        WHERE user_id = %s AND note IS NOT NULL AND note != ''
    """, [session['user_id']])
    note_rows = cur.fetchall()
    notes = {str(row[0]): row[1] for row in note_rows}
    cur.close()

    applications_count = {'applied': 0, 'interview': 0, 'offered': 0, 'rejected': 0}
    for row in rows:
        key = row[0].lower()
        if key in applications_count:
            applications_count[key] = row[1]

    return render_template('dashboard.html',
                           recommended=recommended,
                           others=others,
                           user_name=session['user_name'],
                           applications_count=applications_count,
                           skill_match=skill_match,
                           notes=notes)

# ---- Save Note ----
@app.route('/save-note', methods=['POST'])
def save_note():
    if 'user_id' not in session:
        return jsonify({'status': 'error'}), 401
    data = request.get_json()
    internship_id = data.get('internship_id')
    note = data.get('note', '')
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM applications WHERE user_id = %s AND internship_id = %s",
                (session['user_id'], internship_id))
    existing = cur.fetchone()
    if existing:
        cur.execute("UPDATE applications SET note = %s WHERE user_id = %s AND internship_id = %s",
                    (note, session['user_id'], internship_id))
    else:
        cur.execute("""
            INSERT INTO applications (user_id, internship_id, status, applied_date, note)
            VALUES (%s, %s, %s, %s, %s)
        """, (session['user_id'], internship_id, 'Applied', date.today(), note))
    mysql.connection.commit()
    cur.close()
    return jsonify({'status': 'ok'})

# ---- Internship Detail ----
@app.route('/internship/<int:id>')
def internship_detail(id):
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM internships WHERE id = %s", [id])
    internship = cur.fetchone()
    cur.close()
    return render_template('internship_detail.html', internship=internship)

# ---- Mark as Applied ----
@app.route('/apply/<int:internship_id>')
def apply(internship_id):
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM applications WHERE user_id = %s AND internship_id = %s",
                (session['user_id'], internship_id))
    existing = cur.fetchone()
    if not existing:
        cur.execute(
            "INSERT INTO applications (user_id, internship_id, status, applied_date) VALUES (%s, %s, %s, %s)",
            (session['user_id'], internship_id, 'Applied', date.today())
        )
        mysql.connection.commit()
    cur.close()
    return redirect('/my-applications')

# ---- My Applications ----
@app.route('/my-applications')
def my_applications():
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT a.id, i.title, i.company, i.deadline, a.status, a.applied_date, i.id
        FROM applications a
        JOIN internships i ON a.internship_id = i.id
        WHERE a.user_id = %s
        ORDER BY a.applied_date DESC
    """, [session['user_id']])
    applications = cur.fetchall()
    cur.close()
    return render_template('my_applications.html', applications=applications)

# ---- Update Application Status ----
@app.route('/update-status/<int:app_id>', methods=['POST'])
def update_status(app_id):
    if 'user_id' not in session:
        return redirect('/login')
    new_status = request.form['status']
    cur = mysql.connection.cursor()
    cur.execute("UPDATE applications SET status = %s WHERE id = %s AND user_id = %s",
                (new_status, app_id, session['user_id']))
    mysql.connection.commit()
    cur.close()
    return redirect('/my-applications')

# ---- Profile ----
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        name   = request.form['name']
        skills = request.form['skills']
        cur.execute("UPDATE users SET name = %s, skills = %s WHERE id = %s",
                    (name, skills, session['user_id']))
        mysql.connection.commit()
        session['user_name'] = name
        cur.close()
        return redirect('/dashboard')
    cur.execute("SELECT * FROM users WHERE id = %s", [session['user_id']])
    user = cur.fetchone()
    cur.close()
    return render_template('profile.html', user=user)

# ---- Upload Resume ----
@app.route('/upload-resume', methods=['POST'])
def upload_resume():
    if 'user_id' not in session:
        return redirect('/login')
    if 'resume' not in request.files:
        return redirect('/profile')
    file = request.files['resume']
    if file.filename == '':
        return redirect('/profile')
    if file and allowed_file(file.filename):
        filename = secure_filename(f"user_{session['user_id']}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        cur = mysql.connection.cursor()
        cur.execute("UPDATE users SET resume = %s WHERE id = %s",
                    (filename, session['user_id']))
        mysql.connection.commit()
        cur.close()
    return redirect('/profile')

# ---- View Resume ----
@app.route('/resume/<filename>')
def view_resume(filename):
    if 'user_id' not in session:
        return redirect('/login')
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ---- Delete Resume ----
@app.route('/delete-resume')
def delete_resume():
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("SELECT resume FROM users WHERE id = %s", [session['user_id']])
    user = cur.fetchone()
    if user and user[0]:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], user[0])
        if os.path.exists(filepath):
            os.remove(filepath)
        cur.execute("UPDATE users SET resume = NULL WHERE id = %s", [session['user_id']])
        mysql.connection.commit()
    cur.close()
    return redirect('/profile')

if __name__ == '__main__':
    app.run(debug=True)
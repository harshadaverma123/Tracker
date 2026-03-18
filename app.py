from flask import Flask, render_template, request, redirect, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date

app = Flask(__name__)
app.secret_key = 'smarttracker2024'

# ---- MySQL Config ----
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'zainab13'  # <-- Put your MySQL password here
app.config['MYSQL_DB'] = 'interntrack'

mysql = MySQL(app)

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
    for i in all_internships:
        field = i[4].lower() if i[4] else ''
        title = i[1].lower() if i[1] else ''
        matched = any(skill in field or skill in title for skill in user_skills)
        if matched:
            recommended.append(i)
        else:
            others.append(i)
    cur.close()
    return render_template('dashboard.html',
                           recommended=recommended,
                           others=others,
                           user_name=session['user_name'])

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

if __name__ == '__main__':
    app.run(debug=True)

from flask import Flask, render_template, request, redirect, session, jsonify
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime
import os
from werkzeug.utils import secure_filename
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from collections import Counter
import numpy as np

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

# ---- TF-IDF ----
def get_tfidf_scores(user_skills, internships):
    if not user_skills or not internships:
        return {str(i[0]): 30 for i in internships}
    documents = [f"{i[1]} {i[4]} {i[3]}" for i in internships]
    user_query = ' '.join(user_skills)
    all_docs = documents + [user_query]
    vectorizer = TfidfVectorizer(stop_words='english', lowercase=True)
    tfidf_matrix = vectorizer.fit_transform(all_docs)
    user_vector = tfidf_matrix[-1]
    internship_vectors = tfidf_matrix[:-1]
    similarities = cosine_similarity(user_vector, internship_vectors)[0]
    scores = {}
    for idx, i in enumerate(internships):
        score = int(similarities[idx] * 100)
        score = max(score, 10)
        score = min(score, 99)
        scores[str(i[0])] = score
    return scores

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
            cur.execute("INSERT INTO users (name, email, password, skills) VALUES (%s, %s, %s, %s)",
                        (name, email, password, skills))
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
    skill_match = get_tfidf_scores(user_skills, all_internships)
    recommended = []
    others = []
    for i in all_internships:
        score = skill_match.get(str(i[0]), 10)
        if score >= 40:
            recommended.append(i)
        else:
            others.append(i)
    recommended.sort(key=lambda i: skill_match.get(str(i[0]), 0), reverse=True)
    cur.execute("SELECT status, COUNT(*) as count FROM applications WHERE user_id = %s GROUP BY status", [session['user_id']])
    rows = cur.fetchall()
    cur.execute("SELECT internship_id, note FROM applications WHERE user_id = %s AND note IS NOT NULL AND note != ''", [session['user_id']])
    note_rows = cur.fetchall()
    notes = {str(row[0]): row[1] for row in note_rows}
    cur.execute("SELECT internship_id FROM bookmarks WHERE user_id = %s", [session['user_id']])
    bookmark_rows = cur.fetchall()
    bookmarked_ids = [str(row[0]) for row in bookmark_rows]
    # Get all users for share feature
    cur.execute("SELECT id, name FROM users WHERE id != %s ORDER BY name", [session['user_id']])
    all_users = cur.fetchall()
    cur.close()
    applications_count = {'applied': 0, 'interview': 0, 'offered': 0, 'rejected': 0}
    for row in rows:
        key = row[0].lower()
        if key in applications_count:
            applications_count[key] = row[1]
    return render_template('dashboard.html',
                           recommended=recommended, others=others,
                           user_name=session['user_name'],
                           applications_count=applications_count,
                           skill_match=skill_match, notes=notes,
                           bookmarked_ids=bookmarked_ids,
                           all_users=all_users)

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
        cur.execute("INSERT INTO applications (user_id, internship_id, status, applied_date, note) VALUES (%s, %s, %s, %s, %s)",
                    (session['user_id'], internship_id, 'Applied', date.today(), note))
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
    cur.execute("SELECT id FROM recently_viewed WHERE user_id=%s AND internship_id=%s",
                (session['user_id'], id))
    exists = cur.fetchone()
    if exists:
        cur.execute("UPDATE recently_viewed SET viewed_at=NOW() WHERE user_id=%s AND internship_id=%s",
                    (session['user_id'], id))
    else:
        cur.execute("INSERT INTO recently_viewed (user_id, internship_id) VALUES (%s,%s)",
                    (session['user_id'], id))
    cur.execute("""SELECT r.rating, r.review, u.name, r.created_at
        FROM reviews r JOIN users u ON r.user_id = u.id
        WHERE r.internship_id = %s ORDER BY r.created_at DESC""", [id])
    reviews = cur.fetchall()
    cur.execute("SELECT AVG(rating) FROM reviews WHERE internship_id=%s", [id])
    avg_rating = cur.fetchone()[0]
    avg_rating = round(float(avg_rating), 1) if avg_rating else 0
    cur.execute("SELECT rating, review FROM reviews WHERE user_id=%s AND internship_id=%s",
                (session['user_id'], id))
    user_review = cur.fetchone()
    cur.execute("SELECT id, name, email FROM users WHERE id != %s", [session['user_id']])
    all_users = cur.fetchall()
    mysql.connection.commit()
    cur.close()
    return render_template('internship_detail.html',
                           internship=internship, reviews=reviews,
                           avg_rating=avg_rating, user_review=user_review,
                           all_users=all_users, user_name=session['user_name'])

# ---- Rate and Review ----
@app.route('/review/<int:internship_id>', methods=['POST'])
def review(internship_id):
    if 'user_id' not in session:
        return redirect('/login')
    rating = request.form.get('rating', 3)
    review_text = request.form.get('review', '')
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM reviews WHERE user_id=%s AND internship_id=%s",
                (session['user_id'], internship_id))
    existing = cur.fetchone()
    if existing:
        cur.execute("UPDATE reviews SET rating=%s, review=%s WHERE user_id=%s AND internship_id=%s",
                    (rating, review_text, session['user_id'], internship_id))
    else:
        cur.execute("INSERT INTO reviews (user_id, internship_id, rating, review) VALUES (%s,%s,%s,%s)",
                    (session['user_id'], internship_id, rating, review_text))
    mysql.connection.commit()
    cur.close()
    return redirect(f'/internship/{internship_id}')

# ---- Share Internship ----
@app.route('/share/<int:internship_id>', methods=['POST'])
def share_internship(internship_id):
    if 'user_id' not in session:
        return jsonify({'status': 'error'}), 401
    to_user_id = request.form.get('to_user_id')
    message = request.form.get('message', 'Check out this internship!')
    if not to_user_id:
        return jsonify({'status': 'error', 'msg': 'No user selected'}), 400
    cur = mysql.connection.cursor()
    cur.execute("INSERT INTO shared_internships (from_user_id, to_user_id, internship_id, message) VALUES (%s, %s, %s, %s)",
                (session['user_id'], to_user_id, internship_id, message))
    cur.execute("SELECT name FROM users WHERE id=%s", [session['user_id']])
    sender = cur.fetchone()
    cur.execute("SELECT title FROM internships WHERE id=%s", [internship_id])
    intern = cur.fetchone()
    notif_msg = f"{sender[0]} shared '{intern[0]}' internship with you!"
    cur.execute("INSERT INTO notifications (user_id, message) VALUES (%s,%s)", (to_user_id, notif_msg))
    mysql.connection.commit()
    cur.close()
    return jsonify({'status': 'ok'})

# ---- Notifications ----
@app.route('/notifications')
def notifications():
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM notifications WHERE user_id=%s ORDER BY created_at DESC LIMIT 20", [session['user_id']])
    notifs = cur.fetchall()
    cur.execute("UPDATE notifications SET is_read=1 WHERE user_id=%s", [session['user_id']])
    mysql.connection.commit()
    cur.close()
    return render_template('notifications.html', notifs=notifs, user_name=session['user_name'])

# ---- Notification Count ----
@app.route('/notification-count')
def notification_count():
    if 'user_id' not in session:
        return jsonify({'count': 0})
    cur = mysql.connection.cursor()
    cur.execute("SELECT COUNT(*) FROM notifications WHERE user_id=%s AND is_read=0", [session['user_id']])
    count = cur.fetchone()[0]
    cur.close()
    return jsonify({'count': count})

# ---- Recently Viewed ----
@app.route('/recently-viewed')
def recently_viewed():
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("""SELECT i.*, rv.viewed_at FROM internships i
        JOIN recently_viewed rv ON i.id = rv.internship_id
        WHERE rv.user_id = %s ORDER BY rv.viewed_at DESC LIMIT 10""", [session['user_id']])
    recent = cur.fetchall()
    cur.close()
    return render_template('recently_viewed.html', recent=recent, user_name=session['user_name'])

# ---- Application Timeline ----
@app.route('/timeline/<int:app_id>')
def timeline(app_id):
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("""SELECT ah.status, ah.changed_at, i.title, i.company
        FROM application_history ah
        JOIN applications a ON ah.application_id = a.id
        JOIN internships i ON a.internship_id = i.id
        WHERE ah.application_id = %s AND a.user_id = %s
        ORDER BY ah.changed_at ASC""", (app_id, session['user_id']))
    history = cur.fetchall()
    cur.close()
    return render_template('timeline.html', history=history, user_name=session['user_name'])

# ---- Update Status with Timeline ----
@app.route('/update-status/<int:app_id>', methods=['POST'])
def update_status(app_id):
    if 'user_id' not in session:
        return redirect('/login')
    new_status = request.form['status']
    cur = mysql.connection.cursor()
    cur.execute("UPDATE applications SET status=%s WHERE id=%s AND user_id=%s",
                (new_status, app_id, session['user_id']))
    cur.execute("INSERT INTO application_history (application_id, status) VALUES (%s,%s)",
                (app_id, new_status))
    mysql.connection.commit()
    cur.close()
    return redirect('/my-applications')

# ---- Application Checklist ----
@app.route('/checklist/<int:app_id>', methods=['GET', 'POST'])
def checklist(app_id):
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        resume   = 1 if request.form.get('resume_ready') else 0
        skills   = 1 if request.form.get('skills_match') else 0
        deadline = 1 if request.form.get('deadline_checked') else 0
        cover    = 1 if request.form.get('cover_letter') else 0
        research = 1 if request.form.get('company_researched') else 0
        cur.execute("SELECT id FROM checklist WHERE application_id=%s", [app_id])
        exists = cur.fetchone()
        if exists:
            cur.execute("""UPDATE checklist SET resume_ready=%s, skills_match=%s,
                deadline_checked=%s, cover_letter=%s, company_researched=%s
                WHERE application_id=%s""", (resume, skills, deadline, cover, research, app_id))
        else:
            cur.execute("""INSERT INTO checklist
                (application_id, resume_ready, skills_match, deadline_checked, cover_letter, company_researched)
                VALUES (%s,%s,%s,%s,%s,%s)""", (app_id, resume, skills, deadline, cover, research))
        mysql.connection.commit()
        cur.close()
        return redirect('/my-applications')
    cur.execute("SELECT * FROM checklist WHERE application_id=%s", [app_id])
    check = cur.fetchone()
    cur.execute("""SELECT i.title, i.company, i.deadline FROM applications a
        JOIN internships i ON a.internship_id = i.id
        WHERE a.id=%s AND a.user_id=%s""", (app_id, session['user_id']))
    app_info = cur.fetchone()
    cur.close()
    return render_template('checklist.html', check=check, app_id=app_id,
                           app_info=app_info, user_name=session['user_name'])

# ---- Deadline Calendar ----
@app.route('/calendar')
def deadline_calendar():
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM internships ORDER BY deadline ASC")
    internships = cur.fetchall()
    cur.execute("SELECT internship_id FROM applications WHERE user_id=%s", [session['user_id']])
    applied_ids = [str(row[0]) for row in cur.fetchall()]
    cur.close()
    return render_template('calendar.html', internships=internships,
                           applied_ids=applied_ids, user_name=session['user_name'])

# ---- Skill Gap Analysis ----
@app.route('/skill-gap')
def skill_gap():
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("SELECT skills FROM users WHERE id=%s", [session['user_id']])
    user = cur.fetchone()
    user_skills = [s.strip().lower() for s in user[0].split(',')] if user and user[0] else []
    cur.execute("SELECT * FROM internships")
    internships = cur.fetchall()
    cur.close()
    all_required_skills = []
    gap_data = []
    common_skills = ['python', 'javascript', 'java', 'sql', 'html', 'css',
                    'react', 'flask', 'django', 'machine learning', 'data science',
                    'excel', 'photoshop', 'figma', 'marketing', 'communication',
                    'web development', 'android', 'nodejs', 'php', 'c++']
    for i in internships:
        text = f"{i[1]} {i[4]} {i[3]}".lower()
        required = [s for s in common_skills if s in text]
        missing = [s for s in required if s not in user_skills]
        matched = [s for s in required if s in user_skills]
        match_pct = int((len(matched) / len(required)) * 100) if required else 50
        match_pct = max(match_pct, 10)
        gap_data.append({'title': i[1], 'company': i[2], 'field': i[4],
                         'required': required, 'matched': matched,
                         'missing': missing, 'match_pct': match_pct})
        all_required_skills.extend(missing)
    missing_counts = Counter(all_required_skills).most_common(8)
    gap_data.sort(key=lambda x: x['match_pct'], reverse=True)
    return render_template('skill_gap.html', gap_data=gap_data,
                           missing_counts=missing_counts,
                           user_skills=user_skills, user_name=session['user_name'])

# ---- Analytics ----
@app.route('/analytics')
def analytics():
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("""SELECT i.field, COUNT(a.id) as total FROM applications a
        JOIN internships i ON a.internship_id = i.id GROUP BY i.field ORDER BY total DESC""")
    field_data = cur.fetchall()
    cur.execute("""SELECT i.company, COUNT(a.id) as total FROM applications a
        JOIN internships i ON a.internship_id = i.id GROUP BY i.company
        ORDER BY total DESC LIMIT 6""")
    company_data = cur.fetchall()
    cur.execute("""SELECT DATE_FORMAT(applied_date, '%%b %%Y') as month,
               COUNT(*) as total,
               DATE_FORMAT(applied_date, '%%Y%%m') as sort_key
        FROM applications
        WHERE user_id = %s
        GROUP BY DATE_FORMAT(applied_date, '%%b %%Y'), DATE_FORMAT(applied_date, '%%Y%%m')
        ORDER BY sort_key ASC""", [session['user_id']])
    monthly_data = cur.fetchall()
    cur.execute("SELECT status, COUNT(*) as total FROM applications WHERE user_id = %s GROUP BY status", [session['user_id']])
    status_data = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM applications WHERE user_id = %s", [session['user_id']])
    total_apps = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM internships")
    total_internships = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM bookmarks WHERE user_id = %s", [session['user_id']])
    total_bookmarks = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM applications WHERE user_id = %s AND status = 'Offered'", [session['user_id']])
    total_offered = cur.fetchone()[0]
    cur.close()
    return render_template('analytics.html', user_name=session['user_name'],
                           field_data=field_data, company_data=company_data,
                           monthly_data=monthly_data, status_data=status_data,
                           total_apps=total_apps, total_internships=total_internships,
                           total_bookmarks=total_bookmarks, total_offered=total_offered)

# ---- Bookmark ----
@app.route('/bookmark/<int:internship_id>')
def bookmark(internship_id):
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("SELECT id FROM bookmarks WHERE user_id=%s AND internship_id=%s",
                (session['user_id'], internship_id))
    existing = cur.fetchone()
    if existing:
        cur.execute("DELETE FROM bookmarks WHERE user_id=%s AND internship_id=%s",
                    (session['user_id'], internship_id))
    else:
        cur.execute("INSERT INTO bookmarks (user_id, internship_id) VALUES (%s, %s)",
                    (session['user_id'], internship_id))
    mysql.connection.commit()
    cur.close()
    return redirect('/dashboard')

# ---- Bookmarks Page ----
@app.route('/bookmarks')
def bookmarks():
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("""SELECT i.* FROM internships i
        JOIN bookmarks b ON i.id = b.internship_id
        WHERE b.user_id = %s ORDER BY b.created_at DESC""", [session['user_id']])
    bookmarked = cur.fetchall()
    cur.close()
    return render_template('bookmarks.html', bookmarked=bookmarked, user_name=session['user_name'])

# ---- Compare ----
@app.route('/compare')
def compare():
    if 'user_id' not in session:
        return redirect('/login')
    id1 = request.args.get('id1')
    id2 = request.args.get('id2')
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM internships")
    all_internships = cur.fetchall()
    intern1 = intern2 = None
    if id1:
        cur.execute("SELECT * FROM internships WHERE id=%s", [id1])
        intern1 = cur.fetchone()
    if id2:
        cur.execute("SELECT * FROM internships WHERE id=%s", [id2])
        intern2 = cur.fetchone()
    cur.close()
    return render_template('compare.html', all_internships=all_internships,
                           intern1=intern1, intern2=intern2, user_name=session['user_name'])

# ---- My Applications ----
@app.route('/my-applications')
def my_applications():
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("""SELECT a.id, i.title, i.company, i.deadline, a.status, a.applied_date, i.id
        FROM applications a JOIN internships i ON a.internship_id = i.id
        WHERE a.user_id = %s ORDER BY a.applied_date DESC""", [session['user_id']])
    applications = cur.fetchall()
    cur.close()
    return render_template('my_applications.html', applications=applications)

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
        cur.execute("UPDATE users SET resume = %s WHERE id = %s", (filename, session['user_id']))
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

# ---- Apply ----
@app.route('/apply/<int:internship_id>')
def apply(internship_id):
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM applications WHERE user_id = %s AND internship_id = %s",
                (session['user_id'], internship_id))
    existing = cur.fetchone()
    if not existing:
        cur.execute("INSERT INTO applications (user_id, internship_id, status, applied_date) VALUES (%s, %s, %s, %s)",
                    (session['user_id'], internship_id, 'Applied', date.today()))
        mysql.connection.commit()
    cur.close()
    return redirect('/my-applications')

# ---- Print Report ----
@app.route('/print-report')
def print_report():
    if 'user_id' not in session:
        return redirect('/login')
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM users WHERE id=%s", [session['user_id']])
    user = cur.fetchone()
    cur.execute("""SELECT a.id, i.title, i.company, i.field, i.stipend, i.deadline,
               a.status, a.applied_date FROM applications a
        JOIN internships i ON a.internship_id = i.id
        WHERE a.user_id = %s ORDER BY a.applied_date DESC""", [session['user_id']])
    applications = cur.fetchall()
    cur.close()
    return render_template('print_report.html', user=user,
                           applications=applications,
                           user_name=session['user_name'],
                           now=datetime.now())

if __name__ == '__main__':
    app.run(debug=True)
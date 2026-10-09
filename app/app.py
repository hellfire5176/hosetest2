import os
import io
import secrets
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# Environment Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.environ.get('DATABASE_PATH', '/app/data/hose.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Database Models ---

batch_hose_association = db.Table('batch_hose_association',
    db.Column('batch_id', db.Integer, db.ForeignKey('test_batch.id'), primary_key=True),
    db.Column('hose_id', db.Integer, db.ForeignKey('hose.id'), primary_key=True),
    db.Column('passed', db.Boolean, default=True),
    db.Column('failure_reason', db.String(255), nullable=True)
)

class Hose(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    size_inches = db.Column(db.Float, nullable=False)
    length_feet = db.Column(db.Integer, nullable=False)
    hose_type = db.Column(db.String(50), nullable=False)  # Attack, Supply, Forestry
    status = db.Column(db.String(50), default="In Service")  # In Service, Failed, In Test Layout
    scan_token = db.Column(db.String(64), unique=True, nullable=False)
    last_test_date = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(16)

class TestBatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_date = db.Column(db.DateTime, default=datetime.utcnow)
    tested_by = db.Column(db.String(100), nullable=False)
    target_pressure = db.Column(db.Integer, nullable=False)
    duration_minutes = db.Column(db.Integer, default=5)
    is_active = db.Column(db.Boolean, default=True)
    
    hoses = db.relationship('Hose', secondary=batch_hose_association, 
                            backref=db.backref('test_batches', lazy='dynamic'))

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

# --- NEW: Safe Context Initialization Block ---
# This safely runs outside the web request pool to prevent crashing
with app.app_context():
    db.create_all()

@app.before_request
def check_initial_user():
    # Only verify user population dynamically
    with app.app_context():
        if not User.query.first():
            session['setup_mode'] = True
        else:
            session.pop('setup_mode', None)

# --- Core Routes ---

@app.route('/')
def index():
    hoses = Hose.query.all()
    active_batch = TestBatch.query.filter_by(is_active=True).first()
    return render_template('index.html', hoses=hoses, active_batch=active_batch)

@app.route('/scan/<token>', methods=['GET'])
def scan_hose(token):
    hose = Hose.query.filter_by(scan_token=token).first_or_404()
    active_batch = TestBatch.query.filter_by(is_active=True).first()
    
    if active_batch:
        if hose in active_batch.hoses:
            flash(f"Hose {hose.id} is already in the active test layout.", "info")
        elif hose.status == "Failed":
            flash(f"Cannot add Hose {hose.id}. It is flagged Out of Service!", "danger")
        else:
            active_batch.hoses.append(hose)
            hose.status = "In Test Layout"
            db.session.commit()
            flash(f"Successfully added Hose {hose.id} to active test line layout.", "success")
        return redirect(url_for('index'))
        
    return render_template('hose_view.html', hose=hose)

@app.route('/batch/start', methods=['POST'])
def start_batch():
    tester = request.form.get('tester', 'Firefighter')
    pressure = int(request.form.get('pressure', 300))
    TestBatch.query.filter_by(is_active=True).update({"is_active": False})
    
    new_batch = TestBatch(tested_by=tester, target_pressure=pressure, is_active=True)
    db.session.add(new_batch)
    db.session.commit()
    flash("New batch testing configuration open. Scan or add hoses below.", "success")
    return redirect(url_for('index'))

@app.route('/batch/submit', methods=['POST'])
def submit_batch():
    batch = TestBatch.query.filter_by(is_active=True).first_or_404()
    failed_hose_ids = request.form.getlist('failed_hoses')
    current_time = datetime.utcnow()
    
    for hose in batch.hoses:
        hose.last_test_date = current_time
        if str(hose.id) in failed_hose_ids:
            hose.status = "Failed"
            db.session.execute(
                batch_hose_association.update()
                .where(batch_hose_association.c.batch_id == batch.id)
                .where(batch_hose_association.c.hose_id == hose.id)
                .values(passed=False, failure_reason="Failed pressure containment test")
            )
        else:
            hose.status = "In Service"
            
    batch.is_active = False
    db.session.commit()
    flash("Batch test records successfully captured and saved to inventory.", "success")
    return redirect(url_for('index'))

@app.route('/admin/add-hose', methods=['POST'])
def add_hose():
    h_id = request.form.get('id')
    size = float(request.form.get('size'))
    length = int(request.form.get('length'))
    h_type = request.form.get('type')
    
    if Hose.query.get(h_id):
        flash("Hose ID already exists.", "danger")
    else:
        new_hose = Hose(id=h_id, size_inches=size, length_feet=length, hose_type=h_type, scan_token=Hose.generate_token())
        db.session.add(new_hose)
        db.session.commit()
        flash(f"Hose {h_id} provisioned with unique token.", "success")
    return redirect(url_for('index'))

@app.route('/reports')
def reports_dashboard():
    total_hoses = Hose.query.count()
    in_service = Hose.query.filter_by(status="In Service").count()
    failed_hoses = Hose.query.filter_by(status="Failed").count()
    
    one_year_ago = datetime.utcnow() - timedelta(days=365)
    overdue_hoses = Hose.query.filter(
        (Hose.last_test_date == None) | (Hose.last_test_date < one_year_ago)
    ).filter(Hose.status != "Failed").all()
    
    historical_batches = TestBatch.query.filter_by(is_active=False).order_by(TestBatch.test_date.desc()).all()
    
    return render_template('reports.html', 
                           total=total_hoses, 
                           in_service=in_service, 
                           failed=failed_hoses, 
                           overdue=overdue_hoses,
                           batches=historical_batches)

@app.route('/reports/export/csv')
def export_csv_report():
    hoses = Hose.query.all()
    csv_buffer = io.StringIO()
    csv_buffer.write("Hose ID,Size (Inches),Length (Feet),Hose Type,Operational Status,Last Test Date\n")
    
    for h in hoses:
        t_str = h.last_test_date.strftime('%Y-%m-%d %H:%M') if h.last_test_date else "Never Tested"
        csv_buffer.write(f"{h.id},{h.size_inches},{h.length_feet},{h.hose_type},{h.status},{t_str}\n")
    
    response = Response(csv_buffer.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = f"attachment; filename=hose_compliance_report_{datetime.now().strftime('%Y%m%d')}.csv"
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

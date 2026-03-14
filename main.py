import os
import random
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy.exc import IntegrityError
from sqlalchemy import desc

# ---------------- APP SETUP ----------------
basedir = os.path.abspath(os.path.dirname(__file__))

# Define paths for static and upload folders
static_folder_path = os.path.join(basedir, 'static')
uploads_folder_path = os.path.join(static_folder_path, 'uploads')

# Create directories if they don't exist
if not os.path.exists(static_folder_path):
    os.makedirs(static_folder_path)
if not os.path.exists(uploads_folder_path):
    os.makedirs(uploads_folder_path)

app = Flask(__name__, static_folder=static_folder_path, static_url_path='/static')

# Allow CORS for all domains
CORS(app, resources={r"/*": {"origins": "*"}})

# Configuration
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "kaamconnect.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "dev-secret-key-123")
app.config['UPLOAD_FOLDER'] = uploads_folder_path

db = SQLAlchemy(app)
jwt = JWTManager(app)

# ---------------- CUSTOM ERROR HANDLERS ----------------

@jwt.unauthorized_loader
def missing_token_callback(error):
    return jsonify({
        "message": "Request does not contain an access token.",
        "error": "authorization_required"
    }), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({
        "message": "Signature verification failed. Invalid token.",
        "error": "invalid_token"
    }), 401

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({
        "message": "The token has expired.",
        "error": "token_expired"
    }), 401

# ---------------- CONSTANTS ----------------
APP_NAME = "KaamConnect"

# ---------------- HELPER FUNCTIONS ----------------
def get_logo_url():
    extensions = ['.png', '.jpg', '.jpeg', '.webp', '.svg']
    found_filename = None
    for ext in extensions:
        if os.path.exists(os.path.join(static_folder_path, f"logo{ext}")):
            found_filename = f"logo{ext}"
            break
            
    if found_filename:
        base = request.host_url.rstrip('/')
        return f"{base}/static/{found_filename}"
    return "https://img.icons8.com/fluency/96/handshake.png"

def save_uploaded_file(file_storage, prefix):
    if not file_storage or file_storage.filename == '':
        return ""
    filename = secure_filename(file_storage.filename)
    timestamp = int(datetime.now().timestamp())
    unique_name = f"{prefix}_{timestamp}_{filename}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file_storage.save(file_path)
    return f"/static/uploads/{unique_name}"

# ---------------- DATABASE MODELS ----------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(15), nullable=True)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), nullable=False)  # 'customer' or 'provider'

    provider_type = db.Column(db.String(20), default="professional")
    organization = db.Column(db.String(100), default="")
    
    is_verified = db.Column(db.Boolean, default=False)
    document_image = db.Column(db.Text, default="")
    is_available = db.Column(db.Boolean, default=True)

    full_name = db.Column(db.String(100))
    skill = db.Column(db.String(50))
    
    # Provider Stats (Received when working)
    average_rating = db.Column(db.Float, default=5.0)
    review_count = db.Column(db.Integer, default=0)
    
    # Customer Stats (Received when hiring)
    customer_rating = db.Column(db.Float, default=5.0)
    customer_review_count = db.Column(db.Integer, default=0)
    
    # Wallet Balance
    wallet_balance = db.Column(db.Float, default=0.0)

    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # --- GENERATE UNIQUE WALLET ID ---
    @property
    def wallet_id(self):
        suffix = str(self.id).zfill(4)
        prefix = self.phone[-4:] if self.phone and len(self.phone) >= 4 else "0000"
        return f"WAL-{prefix}-{suffix}"

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "provider_type": self.provider_type,
            "organization": self.organization,
            "full_name": self.full_name or self.username, 
            "skill": self.skill,
            # Provider Metrics
            "rating": round(self.average_rating, 1),
            "reviews": self.review_count,
            # Customer Metrics
            "customer_rating": round(self.customer_rating, 1),
            "customer_reviews": self.customer_review_count,
            "is_verified": self.is_verified,
            "is_available": self.is_available,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "wallet_balance": self.wallet_balance or 0.0,
            "wallet_id": self.wallet_id,
        }

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    address = db.Column(db.String(200))
    is_urgent = db.Column(db.Boolean, default=False)
    price = db.Column(db.Float, default=350.0)
    
    # Status: open, accepted, arrived, in_progress, completed, cancelled, paid
    status = db.Column(db.String(20), default="open") 
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    start_code = db.Column(db.String(10), nullable=True)
    arrival_selfie = db.Column(db.Text, default="")
    work_photo = db.Column(db.Text, default="")

    customer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    customer = db.relationship("User", foreign_keys=[customer_id], backref="posted_jobs")
    provider = db.relationship("User", foreign_keys=[provider_id], backref="accepted_jobs")

    def to_dict(self):
        base_url = request.host_url.rstrip('/')
        arrival_full = f"{base_url}{self.arrival_selfie}" if self.arrival_selfie else ""
        work_full = f"{base_url}{self.work_photo}" if self.work_photo else ""

        # Check if reviews exist
        provider_review = Review.query.filter_by(job_id=self.id, review_type='provider').first()
        customer_review = Review.query.filter_by(job_id=self.id, review_type='customer').first()

        c_name = "Unknown Customer"
        if self.customer:
            c_name = self.customer.full_name or self.customer.username or "Unknown"

        p_name = None
        if self.provider:
             p_name = self.provider.full_name or self.provider.username or "Unknown Provider"

        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "address": self.address,
            "is_urgent": self.is_urgent,
            "status": self.status,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M"),
            "pay": f"₹{int(self.price)}",
            "start_code": self.start_code,
            "arrival_selfie": arrival_full,
            "work_photo": work_full,
            "customer_name": c_name,
            "provider_name": p_name,
            "customer_id": self.customer_id,
            "provider_id": self.provider_id,
            "is_reviewed": provider_review is not None,         # Has provider been rated?
            "is_customer_reviewed": customer_review is not None # Has customer been rated?
        }

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # job_id is NOT unique anymore, allows two reviews per job (one for provider, one for customer)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False) 
    reviewer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reviewee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # 'provider' (review FOR provider) or 'customer' (review FOR customer)
    review_type = db.Column(db.String(20), nullable=False, default='provider')
    
    rating = db.Column(db.Integer, nullable=False) # 1 to 5
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        reviewer = User.query.get(self.reviewer_id)
        return {
            "id": self.id,
            "rating": self.rating,
            "comment": self.comment,
            "review_type": self.review_type,
            "reviewer_name": reviewer.full_name if reviewer else "Anonymous",
            "date": self.created_at.strftime("%Y-%m-%d")
        }

class WithdrawalRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending') # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    user = db.relationship('User', backref=db.backref('withdrawals', lazy=True))

# ---------------- ROUTES ----------------

@app.route('/static/<path:filename>')
def custom_static(filename):
    return send_from_directory(app.static_folder, filename)

@app.route("/")
def index():
    return jsonify({
        "status": "online",
        "message": "KaamConnect Backend V4.5 (Two-Way Reviews)",
        "version": "4.5",
        "endpoints": {
            "auth": "/api/login",
            "providers": "/api/providers",
            "jobs": "/api/jobs",
            "admin": "/admin",
            "wallet": "/api/wallet/balance",
            "review": "/api/jobs/<id>/review",
            "customer_review": "/api/jobs/<id>/review_customer"
        }
    })

@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify({
        "app_name": APP_NAME,
        "app_logo": get_logo_url(),
        "support_email": f"support@{APP_NAME.lower().replace(' ', '')}.com"
    })

# --- AUTH ---
@app.route("/api/register", methods=["POST"])
def register():
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form

    if not data.get("email") or not data.get("password"):
        return jsonify({"message": "Email and Password required", "error": "missing_fields"}), 400

    if User.query.filter_by(email=data.get("email")).first():
        return jsonify({"message": "User with this email already exists", "error": "duplicate_email"}), 400

    user_name = data.get("username") or data.get("email").split("@")[0]
    if User.query.filter_by(username=user_name).first():
        user_name = f"{user_name}{random.randint(100,999)}"

    doc_url = ""
    if 'document_image' in request.files:
        file = request.files['document_image']
        if file.filename != '':
            doc_url = save_uploaded_file(file, 'doc')

    is_customer = data.get("role") == "customer"
    user = User(
        username=user_name,
        email=data.get("email"),
        phone=data.get("phone", ""),
        role=data.get("role", "customer"),
        provider_type=data.get("provider_type", "professional"),
        organization=data.get("organization", ""),
        full_name=data.get("full_name"),
        skill=data.get("skill"),
        latitude=float(data.get("latitude") or 18.5204),
        longitude=float(data.get("longitude") or 73.8567),
        is_verified=is_customer, 
        document_image=doc_url, 
        is_available=True,
        wallet_balance=0.0
    )
    user.set_password(data.get("password"))
    
    try:
        db.session.add(user)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Database error: User already exists.", "error": "integrity_error"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"Server error: {str(e)}", "error": "server_error"}), 500

    return jsonify({"message": "Registration successful", "user": user.to_dict()}), 201

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or request.form
    user = User.query.filter_by(email=data.get("email")).first()
    if user and user.check_password(data.get("password")):
        if user.role == 'provider' and not user.is_verified:
             return jsonify({
                 "message": "Account pending verification or blocked. Please contact Admin.",
                 "error": "account_unverified"
             }), 403
        
        token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
        return jsonify({"token": token, "user": user.to_dict()}), 200
    return jsonify({"message": "Invalid email or password", "error": "bad_credentials"}), 401

@app.route("/api/user/profile", methods=["GET"])
@jwt_required()
def get_profile():
    uid = int(get_jwt_identity())
    user = User.query.get(uid)
    if not user:
        return jsonify({"message": "User not found"}), 404
    return jsonify(user.to_dict())

@app.route("/api/user/availability", methods=["POST"])
@jwt_required()
def toggle_availability():
    uid = int(get_jwt_identity())
    user = User.query.get(uid)
    data = request.get_json() or {}
    
    if "is_available" in data:
        user.is_available = bool(data["is_available"])
    else:
        user.is_available = not user.is_available

    db.session.commit()
    return jsonify({
        "message": "Availability updated", 
        "user": user.to_dict()
    }), 200

# --- WALLET & PAYMENT ROUTES ---

@app.route("/api/wallet/balance", methods=["GET"])
@jwt_required()
def get_wallet_info():
    uid = int(get_jwt_identity())
    user = User.query.get(uid)
    if not user: return jsonify({"message": "User not found"}), 404
    
    return jsonify({
        "balance": user.wallet_balance or 0.0,
        "wallet_id": user.wallet_id
    })

@app.route("/api/wallet/topup", methods=["POST"])
@jwt_required()
def top_up_wallet():
    uid = int(get_jwt_identity())
    user = User.query.get(uid)
    data = request.get_json()
    amount = float(data.get('amount', 0))
    
    if amount <= 0: return jsonify({"message": "Invalid amount"}), 400

    if user.wallet_balance is None: user.wallet_balance = 0.0
    user.wallet_balance += amount
    db.session.commit()
    
    return jsonify({
        "message": "Top Up Successful", 
        "new_balance": user.wallet_balance,
        "txn_id": f"TXN_{random.randint(100000, 999999)}"
    }), 200

@app.route("/api/payment/mock_success", methods=["POST"])
@jwt_required()
def mock_payment_success():
    uid = int(get_jwt_identity())
    data = request.get_json()
    job_id = data.get('job_id')
    
    paid_amount = float(data.get('amount', 0))
    
    job = Job.query.get(job_id)
    if not job: return jsonify({"message": "Job not found"}), 404
    
    final_amount = paid_amount if paid_amount > 0 else job.price

    job.status = 'paid'
    
    if job.provider:
        if job.provider.wallet_balance is None:
            job.provider.wallet_balance = 0.0
        job.provider.wallet_balance += final_amount

    db.session.commit()
    
    return jsonify({
        "message": "Payment Successful",
        "paid_amount": final_amount,
        "transaction_id": f"TXN_{random.randint(10000,99999)}"
    }), 200

@app.route("/api/wallet/withdraw", methods=["POST"])
@jwt_required()
def request_withdraw():
    uid = int(get_jwt_identity())
    user = User.query.get(uid)
    data = request.get_json()
    amount = float(data.get('amount', 0))
    
    if amount <= 0: return jsonify({"message": "Invalid amount"}), 400
    if user.wallet_balance < amount: return jsonify({"message": "Insufficient funds"}), 400
    
    pending = WithdrawalRequest.query.filter_by(user_id=uid, status='pending').first()
    if pending:
        return jsonify({"message": "You already have a pending request. Wait for approval."}), 400

    req = WithdrawalRequest(user_id=uid, amount=amount)
    db.session.add(req)
    db.session.commit()
    
    return jsonify({"message": "Withdrawal request submitted to Admin"}), 200

# --- JOB MANAGEMENT ---

@app.route("/api/jobs", methods=["POST"])
@jwt_required()
def post_job():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    job = Job(
        title=data.get("title"),
        description=data.get("description"),
        category=data.get("category"),
        latitude=float(data.get("latitude")),
        longitude=float(data.get("longitude")),
        address=data.get("address"),
        is_urgent=data.get("is_urgent", False),
        price=float(data.get("price", 350)),
        customer_id=uid
    )
    db.session.add(job)
    db.session.commit()
    return jsonify(job.to_dict()), 201

@app.route("/api/jobs/nearby", methods=["GET"])
@jwt_required()
def get_nearby_jobs():
    jobs = Job.query.filter_by(status="open").order_by(Job.created_at.desc()).all()
    return jsonify([j.to_dict() for j in jobs]), 200

@app.route("/api/jobs/my", methods=["GET"])
@jwt_required()
def get_my_jobs():
    uid = int(get_jwt_identity())
    role = get_jwt().get("role")
    
    if role == "customer":
        jobs = Job.query.filter_by(customer_id=uid).order_by(Job.created_at.desc()).all()
    else:
        jobs = Job.query.filter_by(provider_id=uid).order_by(Job.created_at.desc()).all()
        
    return jsonify([j.to_dict() for j in jobs])

# --- PROVIDER DIRECTORY ---
@app.route("/api/providers", methods=["GET"])
@jwt_required()
def get_all_providers():
    category = request.args.get('category')
    p_type = request.args.get('type')
    
    query = User.query.filter_by(role="provider", is_verified=True, is_available=True)

    if p_type:
        query = query.filter_by(provider_type=p_type)

    if category and category != "All":
        query = query.filter(User.skill.ilike(f"%{category}%"))

    providers = query.all()
    return jsonify([p.to_dict() for p in providers]), 200

# --- JOB WORKFLOW ACTIONS ---

@app.route("/api/jobs/<int:job_id>/accept", methods=["POST"])
@jwt_required()
def accept_job(job_id):
    uid = int(get_jwt_identity())
    user = User.query.get(uid)
    if user.role != "provider":
        return jsonify({"message": "Only providers can accept jobs"}), 403
    job = Job.query.get(job_id)
    if not job or job.status != "open":
        return jsonify({"message": "Job unavailable or already taken"}), 400
    
    otp = str(random.randint(1000, 9999))
    job.provider_id = uid
    job.status = "accepted"
    job.start_code = otp
    db.session.commit()
    return jsonify({"message": "Job accepted.", "job": job.to_dict()}), 200

@app.route("/api/jobs/<int:job_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_job(job_id):
    uid = int(get_jwt_identity())
    job = Job.query.get(job_id)
    
    if not job:
        return jsonify({"message": "Job not found"}), 404

    is_owner = (job.customer_id == uid)
    is_provider = (job.provider_id == uid)

    if not (is_owner or is_provider):
        return jsonify({"message": "Unauthorized action"}), 403

    if job.status in ["completed", "cancelled", "paid"]:
        return jsonify({"message": "Job cannot be cancelled in current state"}), 400
    
    if is_provider and job.status == "in_progress":
        return jsonify({"message": "Cannot cancel after work has started. Contact support."}), 400

    if is_provider:
        job.provider_id = None
        job.status = "open"
        job.start_code = None
        job.arrival_selfie = ""
        msg = "Job dropped. It is now open for others."
    else:
        job.status = "cancelled"
        msg = "Job cancelled successfully."

    db.session.commit()
    return jsonify({"message": msg, "job": job.to_dict()}), 200

@app.route("/api/jobs/<int:job_id>/arrive", methods=["POST"])
@jwt_required()
def mark_arrival(job_id):
    uid = int(get_jwt_identity())
    job = Job.query.get(job_id)
    if not job or job.provider_id != uid:
        return jsonify({"message": "Unauthorized"}), 403
    
    if 'arrival_selfie' in request.files:
        file = request.files['arrival_selfie']
        selfie_url = save_uploaded_file(file, 'arrival')
        job.arrival_selfie = selfie_url
        
    job.status = "arrived"
    db.session.commit()
    return jsonify({"message": "Arrival confirmed.", "job": job.to_dict()}), 200

@app.route("/api/jobs/<int:job_id>/verify_start", methods=["POST"])
@jwt_required()
def verify_start_code(job_id):
    uid = int(get_jwt_identity())
    job = Job.query.get(job_id)
    if not job or job.provider_id != uid:
        return jsonify({"message": "Unauthorized"}), 403
    
    data = request.get_json()
    if str(data.get("code")) == str(job.start_code):
        job.status = "in_progress"
        db.session.commit()
        return jsonify({"message": "Job Started.", "job": job.to_dict()}), 200
    return jsonify({"message": "Invalid OTP", "error": "wrong_otp"}), 400

@app.route("/api/jobs/<int:job_id>/complete", methods=["POST"])
@jwt_required()
def complete_job(job_id):
    uid = int(get_jwt_identity())
    job = Job.query.get(job_id)
    if not job or job.provider_id != uid:
        return jsonify({"message": "Unauthorized"}), 403
    
    work_url = ""
    if 'work_photo' in request.files:
        work_url = save_uploaded_file(request.files['work_photo'], 'work')
        job.work_photo = work_url
        
    job.status = "completed"
    db.session.commit()
    return jsonify({"message": "Job Completed!", "job": job.to_dict()}), 200

# --- TWO-WAY REVIEW SYSTEM ---

@app.route("/api/jobs/<int:job_id>/review", methods=["POST"])
@jwt_required()
def post_provider_review(job_id):
    """Customer reviews Provider"""
    uid = int(get_jwt_identity())
    data = request.get_json()
    
    job = Job.query.get(job_id)
    if not job or job.customer_id != uid: return jsonify({"message": "Unauthorized"}), 403
    if job.status not in ["completed", "paid"]: return jsonify({"message": "Job must be finished"}), 400
    
    if Review.query.filter_by(job_id=job_id, review_type='provider').first():
        return jsonify({"message": "Already reviewed provider"}), 400

    rating = int(data.get("rating", 5))
    review = Review(
        job_id=job_id, reviewer_id=uid, reviewee_id=job.provider_id,
        review_type='provider', rating=rating, comment=data.get("comment", "")
    )
    db.session.add(review)

    # Recalculate Provider Rating
    provider = User.query.get(job.provider_id)
    all_revs = Review.query.filter_by(reviewee_id=provider.id, review_type='provider').all()
    total = sum([r.rating for r in all_revs]) + rating
    count = len(all_revs) + 1
    provider.average_rating = total / count
    provider.review_count = count

    db.session.commit()
    return jsonify({"message": "Review submitted successfully"}), 201

@app.route("/api/jobs/<int:job_id>/review_customer", methods=["POST"])
@jwt_required()
def post_customer_review(job_id):
    """Provider reviews Customer"""
    uid = int(get_jwt_identity())
    data = request.get_json()
    
    job = Job.query.get(job_id)
    if not job or job.provider_id != uid: return jsonify({"message": "Unauthorized"}), 403
    
    if Review.query.filter_by(job_id=job_id, review_type='customer').first():
        return jsonify({"message": "Already reviewed customer"}), 400

    rating = int(data.get("rating", 5))
    review = Review(
        job_id=job_id, reviewer_id=uid, reviewee_id=job.customer_id,
        review_type='customer', rating=rating, comment=data.get("comment", "")
    )
    db.session.add(review)

    # Recalculate Customer Rating
    customer = User.query.get(job.customer_id)
    all_revs = Review.query.filter_by(reviewee_id=customer.id, review_type='customer').all()
    total = sum([r.rating for r in all_revs]) + rating
    count = len(all_revs) + 1
    customer.customer_rating = total / count
    customer.customer_review_count = count

    db.session.commit()
    return jsonify({"message": "Customer review submitted"}), 201

@app.route("/api/providers/<int:provider_id>/reviews", methods=["GET"])
def get_provider_reviews(provider_id):
    reviews = Review.query.filter_by(reviewee_id=provider_id, review_type='provider').order_by(Review.created_at.desc()).all()
    return jsonify([r.to_dict() for r in reviews]), 200

@app.route("/api/customers/<int:customer_id>/reviews", methods=["GET"])
def get_customer_reviews(customer_id):
    reviews = Review.query.filter_by(reviewee_id=customer_id, review_type='customer').order_by(Review.created_at.desc()).all()
    return jsonify([r.to_dict() for r in reviews]), 200

# ---------------- ADMIN PANEL ----------------
@app.route("/admin")
def admin_dashboard():
    pending = User.query.filter_by(role="provider", is_verified=False).all()
    approved = User.query.filter_by(role="provider", is_verified=True).all()
    withdrawals = WithdrawalRequest.query.filter_by(status='pending').all()
    
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Admin</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.7.2/font/bootstrap-icons.css">
        <style>
            .card { box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: none; }
            .card-header { font-weight: bold; }
        </style>
    </head>
    <body class="bg-light">
        <nav class="navbar navbar-dark bg-dark mb-4">
            <div class="container-fluid"><span class="navbar-brand mb-0 h1">KaamConnect Admin Panel</span></div>
        </nav>
        <div class="container">
            <div class="row">
                <!-- Pending Section -->
                <div class="col-md-4 mb-4">
                    <div class="card h-100">
                        <div class="card-header bg-warning text-dark d-flex justify-content-between align-items-center">
                            <span>Pending Verification</span>
                            <span class="badge bg-light text-dark">{{ pending|length }}</span>
                        </div>
                        <div class="card-body">
                            {% if pending %}
                                {% for u in pending %}
                                <div class="card mb-3 border-warning">
                                    <div class="card-body">
                                        <h6 class="card-title">{{ u.full_name }} ({{ u.username }})</h6>
                                        <p class="card-text small mb-2 text-muted">
                                            Role: {{ u.provider_type }} | Skill: {{ u.skill }}<br>
                                            <i class="bi bi-envelope"></i> {{ u.email }}<br>
                                            <i class="bi bi-phone"></i> {{ u.phone }}
                                        </p>
                                        <div class="d-flex justify-content-between align-items-center mt-3">
                                            {% if u.document_image %}
                                            <a href="{{ u.document_image }}" target="_blank" class="btn btn-sm btn-outline-primary">View ID</a>
                                            {% else %}
                                            <span class="text-muted small">No ID</span>
                                            {% endif %}
                                            <form action="{{ url_for('approve_user', user_id=u.id) }}" method="POST">
                                                <button class="btn btn-success btn-sm">Approve</button>
                                            </form>
                                        </div>
                                    </div>
                                </div>
                                {% endfor %}
                            {% else %}
                                <div class="text-center text-muted py-4"><p>No pending requests.</p></div>
                            {% endif %}
                        </div>
                    </div>
                </div>

                <!-- Withdrawal Requests Section -->
                <div class="col-md-4 mb-4">
                    <div class="card h-100 border-primary">
                        <div class="card-header bg-primary text-white d-flex justify-content-between align-items-center">
                            <span>Withdrawals</span>
                            <span class="badge bg-light text-primary">{{ withdrawals|length }}</span>
                        </div>
                        <div class="card-body">
                            {% if withdrawals %}
                                {% for w in withdrawals %}
                                <div class="card mb-3 border-primary">
                                    <div class="card-body">
                                        <div class="d-flex justify-content-between align-items-start mb-2">
                                            <div>
                                                <h5 class="text-primary m-0">₹{{ w.amount }}</h5>
                                                <small class="text-muted" style="font-size: 0.75rem;">
                                                    <i class="bi bi-clock"></i> {{ w.created_at.strftime('%Y-%m-%d %H:%M') }}
                                                </small>
                                            </div>
                                        </div>
                                        <div class="p-2 bg-light rounded border mb-2">
                                            <p class="card-text small mb-0">
                                                <strong>{{ w.user.full_name }}</strong> <span class="badge bg-secondary" style="font-size: 0.65rem;">{{ w.user.skill }}</span><br>
                                                <i class="bi bi-envelope"></i> {{ w.user.email }}<br>
                                                <i class="bi bi-phone"></i> {{ w.user.phone }}<br>
                                                Rating: <span class="text-warning">★ {{ "%.1f"|format(w.user.average_rating) }}</span><br>
                                                Wallet: <strong class="text-success">₹{{ w.user.wallet_balance }}</strong>
                                            </p>
                                        </div>
                                        <div class="d-flex justify-content-end gap-2">
                                            <form action="{{ url_for('handle_withdrawal', req_id=w.id, action='reject') }}" method="POST" class="d-inline">
                                                <button class="btn btn-sm btn-outline-danger me-1">Reject</button>
                                            </form>
                                            <form action="{{ url_for('handle_withdrawal', req_id=w.id, action='approve') }}" method="POST" class="d-inline">
                                                <button class="btn btn-sm btn-success">Approve</button>
                                            </form>
                                        </div>
                                    </div>
                                </div>
                                {% endfor %}
                            {% else %}
                                <div class="text-center text-muted py-4"><p>No pending withdrawals.</p></div>
                            {% endif %}
                        </div>
                    </div>
                </div>

                <!-- Active Partners Section -->
                <div class="col-md-4 mb-4">
                    <div class="card h-100">
                        <div class="card-header bg-success text-white d-flex justify-content-between align-items-center">
                            <span>Active Partners</span>
                            <span class="badge bg-light text-dark">{{ approved|length }}</span>
                        </div>
                        <div class="card-body">
                            {% if approved %}
                                {% for u in approved %}
                                <div class="card mb-3 border-success">
                                    <div class="card-body">
                                        <div class="d-flex justify-content-between align-items-start">
                                            <div>
                                                <h6 class="card-title mb-1">{{ u.full_name }}</h6>
                                                <small class="text-muted d-block mb-1">
                                                    <i class="bi bi-envelope"></i> {{ u.email }} | <i class="bi bi-phone"></i> {{ u.phone }}
                                                </small>
                                                <div class="mb-1 text-warning small">
                                                    ★ {{ "%.1f"|format(u.average_rating) }} ({{ u.review_count }} reviews)
                                                </div>
                                                <span class="badge {{ 'bg-success' if u.is_available else 'bg-secondary' }} mb-2">
                                                    {{ 'Online' if u.is_available else 'Offline' }}
                                                </span>
                                            </div>
                                            <form action="{{ url_for('block_user', user_id=u.id) }}" method="POST">
                                                <button class="btn btn-outline-danger btn-sm">Block</button>
                                            </form>
                                        </div>
                                        <p class="card-text small text-muted">
                                            {{ u.skill }} ({{ u.provider_type }})<br>
                                            <strong>Wallet:</strong> ₹{{ u.wallet_balance }}
                                        </p>
                                    </div>
                                </div>
                                {% endfor %}
                            {% else %}
                                <div class="text-center text-muted py-4"><p>No verified providers yet.</p></div>
                            {% endif %}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(html, pending=pending, approved=approved, withdrawals=withdrawals)
@app.route("/admin/approve/<int:user_id>", methods=["POST"])
def approve_user(user_id):
    user = User.query.get(user_id)
    if user:
        user.is_verified = True
        db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/block/<int:user_id>", methods=["POST"])
def block_user(user_id):
    user = User.query.get(user_id)
    if user:
        user.is_verified = False
        user.is_available = False
        db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/withdraw/<int:req_id>/<action>", methods=["POST"])
def handle_withdrawal(req_id, action):
    req = WithdrawalRequest.query.get(req_id)
    if req and req.status == 'pending':
        if action == 'approve':
            if req.user.wallet_balance >= req.amount:
                req.user.wallet_balance -= req.amount
                req.status = 'approved'
                db.session.commit()
            else:
                req.status = 'rejected'
                db.session.commit()
        elif action == 'reject':
            req.status = 'rejected'
            db.session.commit()
    return redirect(url_for('admin_dashboard'))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
"""CampusConnect backend: users, posts, comments, votes, resources, reports."""
from datetime import datetime
from functools import wraps

from flask import Flask, jsonify, request, session, render_template
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-before-deploying"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///campusconnect.db"
db = SQLAlchemy(app)

CATEGORIES = ["DSA", "Academics", "Internships", "Placements", "Hackathons", "Career"]
RESOURCE_TYPES = ["Sell", "Lend", "Donate", "Exchange"]


# ---------- Models ----------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    year = db.Column(db.Integer, default=1)  # 1 = first year; seniors are 2+
    skills = db.Column(db.String(200), default="")
    is_admin = db.Column(db.Boolean, default=False)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, default="")
    category = db.Column(db.String(30), nullable=False)
    is_anonymous = db.Column(db.Boolean, default=False)
    reported = db.Column(db.Boolean, default=False)
    created = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship("User")
    comments = db.relationship("Comment", backref="post", cascade="all, delete-orphan")
    votes = db.relationship("Vote", backref="post", cascade="all, delete-orphan")


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    created = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship("User")


class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("post_id", "user_id"),)  # one vote per user


class Resource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    rtype = db.Column(db.String(20), nullable=False)
    category = db.Column(db.String(30), default="Other")
    condition = db.Column(db.String(20), default="Good")
    owner = db.relationship("User")


# ---------- Helpers ----------
def current_user():
    uid = session.get("uid")
    return db.session.get(User, uid) if uid else None


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user():
            return jsonify(error="Please log in first"), 401
        return f(*a, **kw)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        u = current_user()
        if not u or not u.is_admin:
            return jsonify(error="Moderators only"), 403
        return f(*a, **kw)
    return wrapper


def post_json(p, viewer):
    """Anonymous posts hide the author unless the viewer is a moderator."""
    show_real = (not p.is_anonymous) or (viewer and viewer.is_admin)
    return {
        "id": p.id, "title": p.title, "body": p.body, "category": p.category,
        "anonymous": p.is_anonymous,
        "author": p.author.name if show_real else "Anonymous",
        "votes": len(p.votes), "reported": p.reported,
        "comments": [
            {"id": c.id, "text": c.text,
             "author": c.author.name + (" (senior)" if c.author.year > 1 else "")}
            for c in p.comments],
        "created": p.created.isoformat(),
    }


# ---------- Pages ----------
@app.route("/")
def home():
    return render_template("index.html")


# ---------- Auth ----------
@app.post("/api/register")
def register():
    d = request.get_json(force=True)
    if not all(d.get(k) for k in ("name", "email", "password")):
        return jsonify(error="Name, email and password are required"), 400
    if User.query.filter_by(email=d["email"].lower()).first():
        return jsonify(error="That email is already registered"), 409
    u = User(name=d["name"], email=d["email"].lower(),
             password_hash=generate_password_hash(d["password"]),
             year=int(d.get("year", 1)))
    db.session.add(u)
    db.session.commit()
    session["uid"] = u.id
    return jsonify(ok=True, name=u.name)


@app.post("/api/login")
def login():
    d = request.get_json(force=True)
    u = User.query.filter_by(email=d.get("email", "").lower()).first()
    if not u or not check_password_hash(u.password_hash, d.get("password", "")):
        return jsonify(error="Wrong email or password"), 401
    session["uid"] = u.id
    return jsonify(ok=True, name=u.name, admin=u.is_admin)


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


# ---------- Posts ----------
@app.get("/api/posts")
def list_posts():
    q = Post.query
    cat = request.args.get("category")
    if cat:
        q = q.filter_by(category=cat)
    search = request.args.get("q", "").strip()
    if search:  # simple keyword search; replace with semantic search later
        like = f"%{search}%"
        q = q.filter(Post.title.ilike(like) | Post.body.ilike(like))
    posts = q.order_by(Post.created.desc()).all()
    viewer = current_user()
    return jsonify([post_json(p, viewer) for p in posts])


@app.post("/api/posts")
@login_required
def create_post():
    d = request.get_json(force=True)
    if not d.get("title") or d.get("category") not in CATEGORIES:
        return jsonify(error="A title and a valid category are required"), 400
    p = Post(author_id=current_user().id, title=d["title"], body=d.get("body", ""),
             category=d["category"], is_anonymous=bool(d.get("anonymous")))
    db.session.add(p)
    db.session.commit()
    return jsonify(post_json(p, current_user())), 201


@app.post("/api/posts/<int:pid>/comments")
@login_required
def add_comment(pid):
    p = db.get_or_404(Post, pid)
    text = request.get_json(force=True).get("text", "").strip()
    if not text:
        return jsonify(error="Comment cannot be empty"), 400
    db.session.add(Comment(post_id=p.id, author_id=current_user().id, text=text))
    db.session.commit()
    return jsonify(post_json(p, current_user()))


@app.post("/api/posts/<int:pid>/vote")
@login_required
def toggle_vote(pid):
    p = db.get_or_404(Post, pid)
    uid = current_user().id
    v = Vote.query.filter_by(post_id=pid, user_id=uid).first()
    if v:
        db.session.delete(v)
    else:
        db.session.add(Vote(post_id=pid, user_id=uid))
    db.session.commit()
    return jsonify(votes=Vote.query.filter_by(post_id=pid).count())


@app.post("/api/posts/<int:pid>/report")
@login_required
def report_post(pid):
    p = db.get_or_404(Post, pid)
    p.reported = True
    db.session.commit()
    return jsonify(ok=True)


# ---------- Resources ----------
@app.get("/api/resources")
def list_resources():
    q = Resource.query
    for field in ("rtype", "category", "condition"):
        if request.args.get(field):
            q = q.filter(getattr(Resource, field) == request.args[field])
    return jsonify([{"id": r.id, "name": r.name, "type": r.rtype, "category": r.category,
                     "condition": r.condition, "owner": r.owner.name} for r in q.all()])


@app.post("/api/resources")
@login_required
def add_resource():
    d = request.get_json(force=True)
    if not d.get("name") or d.get("rtype") not in RESOURCE_TYPES:
        return jsonify(error="A name and a valid type are required"), 400
    r = Resource(owner_id=current_user().id, name=d["name"], rtype=d["rtype"],
                 category=d.get("category", "Other"), condition=d.get("condition", "Good"))
    db.session.add(r)
    db.session.commit()
    return jsonify(ok=True, id=r.id), 201


# ---------- Moderation ----------
@app.get("/api/admin/reports")
@admin_required
def reports():
    posts = Post.query.filter_by(reported=True).all()
    return jsonify([post_json(p, current_user()) for p in posts])


@app.post("/api/admin/posts/<int:pid>/<action>")
@admin_required
def moderate(pid, action):
    p = db.get_or_404(Post, pid)
    if action == "remove":
        db.session.delete(p)
    elif action == "dismiss":
        p.reported = False
    else:
        return jsonify(error="Unknown action"), 400
    db.session.commit()
    return jsonify(ok=True)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)

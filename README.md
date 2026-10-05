# CampusConnect (Syrus 7.0, PS4)

## Setup
    python -m venv venv
    venv\Scripts\activate        # Windows  (Mac/Linux: source venv/bin/activate)
    pip install -r requirements.txt
    python app.py                # open http://127.0.0.1:5000

## Structure
    app.py            models + API routes
    templates/        HTML pages (index.html)
    static/           CSS, JS, images
    requirements.txt  dependencies

## API
    POST /api/register  /api/login  /api/logout
    GET  /api/posts?category=DSA&q=roadmap     POST /api/posts
    POST /api/posts/<id>/comments  /vote  /report
    GET  /api/resources?rtype=Sell             POST /api/resources
    GET  /api/admin/reports                    POST /api/admin/posts/<id>/remove|dismiss

## Make yourself a moderator
    flask shell
    >>> u = User.query.filter_by(email="you@example.com").first(); u.is_admin = True; db.session.commit()

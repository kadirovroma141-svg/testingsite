"""
api/index.py — Vercel serverless entry point.

Vercel expects to find the Flask `app` object in this file.
We import the Application Factory from the parent directory and expose `app`
at module level so Vercel's @vercel/python runtime can pick it up.
"""
import os
import sys

# ---------------------------------------------------------------------------
# Make the project root importable (parent of the `api/` folder)
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ---------------------------------------------------------------------------
# Force production config when running inside Vercel
# (VERCEL env var is set automatically by the platform)
# ---------------------------------------------------------------------------
if os.environ.get("VERCEL"):
    os.environ.setdefault("FLASK_ENV", "production")

# ---------------------------------------------------------------------------
# Create the Flask application
# ---------------------------------------------------------------------------
from app import create_app  # noqa: E402  (import after sys.path manipulation)

app = create_app()

# ---------------------------------------------------------------------------
# One-time DB initialisation route.
# Visit  /init-db  ONCE after the first deploy to create all tables.
# Remove or protect this route afterwards!
# ---------------------------------------------------------------------------
from flask import jsonify  # noqa: E402


@app.route("/init-db")
def init_db():
    """Create all database tables (run once after first deploy)."""
    from models import db
    with app.app_context():
        db.create_all()
    return jsonify({"status": "ok", "message": "Таблицы созданы / уже существуют."})

import sqlite3
import string
import random
from flask import Flask, request, redirect, jsonify, render_template, g, abort

app = Flask(__name__)

DATABASE = "urls.db"
SHORT_CODE_LENGTH = 6
ALPHABET = string.ascii_letters + string.digits


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    """Get a per-request database connection."""
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    """Create the urls table if it doesn't exist."""
    with sqlite3.connect(DATABASE) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                short_code TEXT UNIQUE NOT NULL,
                long_url TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                clicks INTEGER DEFAULT 0
            )
            """
        )
        db.commit()


# ---------------------------------------------------------------------------
# Short code generation
# ---------------------------------------------------------------------------
def generate_short_code(length=SHORT_CODE_LENGTH):
    """Generate a random alphanumeric short code, retrying on collision."""
    db = get_db()
    while True:
        code = "".join(random.choices(ALPHABET, k=length))
        existing = db.execute(
            "SELECT 1 FROM urls WHERE short_code = ?", (code,)
        ).fetchone()
        if not existing:
            return code


def is_valid_url(url):
    """Very small sanity check for URL-ish input."""
    return isinstance(url, str) and url.strip().startswith(("http://", "https://"))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/shorten", methods=["POST"])
def shorten_url():
    data = request.get_json(silent=True) or {}
    long_url = data.get("url", "").strip()

    if not long_url:
        return jsonify({"error": "Missing 'url' field"}), 400

    if not is_valid_url(long_url):
        return jsonify({"error": "URL must start with http:// or https://"}), 400

    db = get_db()

    # If this long URL was already shortened, return the existing code
    existing = db.execute(
        "SELECT short_code FROM urls WHERE long_url = ?", (long_url,)
    ).fetchone()
    if existing:
        short_code = existing["short_code"]
    else:
        short_code = generate_short_code()
        db.execute(
            "INSERT INTO urls (short_code, long_url) VALUES (?, ?)",
            (short_code, long_url),
        )
        db.commit()

    short_url = request.host_url + short_code
    return jsonify(
        {
            "short_code": short_code,
            "short_url": short_url,
            "long_url": long_url,
        }
    ), 201


@app.route("/api/urls", methods=["GET"])
def list_urls():
    """List all shortened URLs (handy for debugging / the frontend table)."""
    db = get_db()
    rows = db.execute(
        "SELECT short_code, long_url, created_at, clicks FROM urls ORDER BY id DESC"
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/<short_code>")
def redirect_to_long_url(short_code):
    db = get_db()
    row = db.execute(
        "SELECT long_url FROM urls WHERE short_code = ?", (short_code,)
    ).fetchone()

    if row is None:
        abort(404)

    db.execute(
        "UPDATE urls SET clicks = clicks + 1 WHERE short_code = ?", (short_code,)
    )
    db.commit()

    return redirect(row["long_url"])


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Short URL not found"}), 404


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)

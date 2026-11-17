import os
import sqlite3
import hmac
from datetime import datetime, timezone
from flask import Flask, request, jsonify, render_template, abort

app = Flask(__name__)
DB_PATH = os.getenv("DATABASE_PATH", "builds.db")
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "change-this-demo-token")


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS builds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                project TEXT NOT NULL,
                branch TEXT,
                commit_sha TEXT,
                build_number TEXT,
                status TEXT NOT NULL,
                build_url TEXT,
                failure_reason TEXT,
                diagnosis TEXT,
                recommendation TEXT,
                received_at TEXT NOT NULL,
                delivery_id TEXT UNIQUE
            )
        """)


init_db()  # Also initialize when deployed through a WSGI server.


def diagnose(reason, status):
    """A small, transparent rule-based MVP. Add an AI provider later if needed."""
    text = (reason or "").lower()

    rules = [
        (["modulenotfounderror", "no module named", "module not found"],
         "A required Python package or module could not be found.",
         "Check requirements.txt and install dependencies, for example: pip install -r requirements.txt."),
        (["could not find", "package not found", "npm err! code enotfound"],
         "A dependency could not be downloaded or resolved.",
         "Check the package name, registry/network access, and lockfile; then reinstall dependencies."),
        (["syntaxerror", "syntax error", "unexpected token"],
         "The source code contains a syntax error.",
         "Open the referenced file and line in the build log, correct the syntax, and rerun the pipeline."),
        (["assertionerror", "test failed", "tests failed", "failed (", "failure in"],
         "One or more automated tests failed.",
         "Open the test report, identify the failing assertion, and fix the code or update an incorrect test."),
        (["permission denied", "eacces", "access is denied"],
         "The build process does not have permission to access a file or command.",
         "Check file permissions, runner/agent permissions, and whether the required executable is available."),
        (["connection refused", "timed out", "timeout", "could not resolve host"],
         "A network service or external dependency could not be reached.",
         "Check the service URL, network access, firewall rules, and whether the dependent service is running."),
        (["cannot find symbol", "compilation error", "javac"],
         "The Java compilation step failed.",
         "Check the compiler output for the first reported file and line; verify class names, imports, and JDK version."),
        (["out of memory", "oomkilled", "killed process"],
         "The build may have exceeded its available memory.",
         "Reduce parallel build work, increase runner/agent memory, or inspect memory-heavy test/build steps."),
    ]

    if status == "SUCCESS":
        return ("No failure detected.", "No action required.")
    for needles, diagnosis, recommendation in rules:
        if any(n in text for n in needles):
            return diagnosis, recommendation

    return (
        "The build failed, but the available error text does not match a known pattern.",
        "Open the build log using the build URL, find the first meaningful error (not just the final 'build failed' line), and add that message to the failure details."
    )


def normalize_status(value):
    value = (value or "UNKNOWN").upper()
    mapping = {
        "SUCCESS": "SUCCESS", "SUCCEEDED": "SUCCESS", "PASSED": "SUCCESS",
        "FAILURE": "FAILURE", "FAILED": "FAILURE", "CANCELED": "ABORTED",
        "CANCELLED": "ABORTED", "ABORTED": "ABORTED", "UNSTABLE": "UNSTABLE",
        "TIMED_OUT": "FAILURE"
    }
    return mapping.get(value, value if value in {"SUCCESS", "FAILURE", "UNSTABLE", "ABORTED"} else "UNKNOWN")


def authorized():
    supplied = request.headers.get("X-Webhook-Token", "")
    return bool(WEBHOOK_TOKEN) and hmac.compare_digest(supplied, WEBHOOK_TOKEN)


@app.get("/")
def dashboard():
    with db() as conn:
        rows = conn.execute("SELECT * FROM builds ORDER BY id DESC LIMIT 100").fetchall()
        counts = conn.execute("""
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN status='SUCCESS' THEN 1 ELSE 0 END) AS success,
              SUM(CASE WHEN status='FAILURE' THEN 1 ELSE 0 END) AS failure
            FROM builds
        """).fetchone()
    return render_template("index.html", builds=rows, counts=counts)


@app.post("/webhooks/<provider>")
def receive_build(provider):
    if not authorized():
        abort(401, description="Invalid webhook token")

    if provider not in {"jenkins", "github-actions", "gitlab"}:
        abort(404)

    data = request.get_json(silent=True) or {}
    status = normalize_status(data.get("status") or data.get("conclusion"))
    reason = (data.get("failure_reason") or data.get("error") or "")[:8000]
    diagnosis, recommendation = diagnose(reason, status)

    delivery_id = request.headers.get("X-Delivery-ID") or data.get("delivery_id")
    received_at = datetime.now(timezone.utc).isoformat()

    try:
        with db() as conn:
            conn.execute("""
                INSERT INTO builds
                (provider, project, branch, commit_sha, build_number, status,
                 build_url, failure_reason, diagnosis, recommendation, received_at, delivery_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                provider,
                str(data.get("project") or data.get("repository") or "Unknown project")[:250],
                str(data.get("branch") or "")[:250],
                str(data.get("commit") or data.get("commit_sha") or "")[:100],
                str(data.get("build_number") or data.get("run_number") or "")[:100],
                status,
                str(data.get("build_url") or data.get("url") or "")[:1000],
                reason,
                diagnosis,
                recommendation,
                received_at,
                delivery_id
            ))
    except sqlite3.IntegrityError:
        # A repeated delivery ID is treated as an already-processed event.
        return jsonify({"received": True, "duplicate": True}), 200

    return jsonify({
        "received": True,
        "provider": provider,
        "status": status,
        "diagnosis": diagnosis
    }), 202


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    # Local development only. Use a production WSGI server for deployment.
    app.run(host="127.0.0.1", port=5000, debug=True)

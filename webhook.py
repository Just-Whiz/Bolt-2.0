import hashlib
import hmac
import logging
import os
import subprocess

from dotenv import load_dotenv
from flask import Flask, abort, request

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_DIR  = os.getenv("PROJECT_DIR", "/home/justwhiz/Desktop/GardeProjects/Bolt-2.0")
PM2_APP_NAME = os.getenv("PM2_APP_NAME", "bolt-bot")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
PORT = int(os.getenv("WEBHOOK_PORT", 9000))
BRANCH = os.getenv("GIT_BRANCH", "main")
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)


def _verify(payload: bytes, sig_header: str) -> bool:
    """Return True if the GitHub signature matches our secret."""
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header or "")


def _run(cmd: list[str]) -> str:
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=PROJECT_DIR
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return result.stdout.strip()


@app.route("/webhook", methods=["POST"])
def webhook():
    # 1. Verify the request is really from GitHub
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not _verify(request.data, sig):
        log.warning("Invalid signature — request rejected")
        abort(401)

    # 2. Only act on pushes to the target branch
    payload = request.get_json(silent=True) or {}
    ref = payload.get("ref", "")
    if ref != f"refs/heads/{BRANCH}":
        log.info("Push to %s ignored (watching %s)", ref, BRANCH)
        return "ignored", 200

    log.info("Push received — fetching and force-resetting…")

    try:
        # Download the latest data from GitHub without merging yet
        out = _run(["git", "fetch", "origin", BRANCH])
        log.info("git fetch: %s", out)

        # Force the local branch to match the remote tracking branch.
        # This obliterates any local staged or unstaged modifications.
        out = _run(["git", "reset", "--hard", f"origin/{BRANCH}"])
        log.info("git reset: %s", out)

        # Restart the bot process
        out = _run(["pm2", "restart", PM2_APP_NAME])
        log.info("pm2 restart: %s", out)
    except RuntimeError as exc:
        log.error("Deploy failed: %s", exc)
        return f"deploy error: {exc}", 500

    log.info("Deploy complete ✓")
    return "ok", 200


if __name__ == "__main__":
    log.info(
        "Webhook listening on :%s | project=%s | app=%s | branch=%s",
        PORT, PROJECT_DIR, PM2_APP_NAME, BRANCH,
    )
    app.run(host="0.0.0.0", port=PORT)
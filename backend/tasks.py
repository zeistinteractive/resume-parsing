import json
import os
from dotenv import load_dotenv

load_dotenv()

import redis as sync_redis
from celery.exceptions import SoftTimeLimitExceeded

from celery_app import celery
from database import update_resume_parsed, update_resume_failed
from parser import extract_text
from ai_parser import parse_resume

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")


def _publish_status(resume_id: int, status: str, candidate_name: str = None):
    """
    Publish a parse-status event to the 'resume_events' Redis channel.
    The SSE endpoint in events.py forwards this to every connected browser.
    """
    try:
        r = sync_redis.from_url(REDIS_URL)
        payload = json.dumps({
            "resume_id":      resume_id,
            "status":         status,
            "candidate_name": candidate_name,
        })
        r.publish("resume_events", payload)
        r.close()
    except Exception as e:
        # Non-fatal — DB is already updated; SSE is best-effort
        print(f"⚠️  Failed to publish SSE event for resume {resume_id}: {e}")


@celery.task(
    bind=True,
    name="tasks.parse_resume",
    max_retries=3,
    time_limit=180,
    soft_time_limit=150,
)
def parse_resume_task(self, resume_id: int, file_path: str):
    """
    Celery task: extract text → AI parse → write to DB → push SSE event.

    Retries up to 3 times with exponential backoff (30s → 60s → 120s).
    Killed after 3 minutes to prevent Gemini API hangs.
    """
    try:
        print(f"📄 [Task {self.request.id}] Extracting text for resume {resume_id}...")
        raw_text = extract_text(file_path)

        if not raw_text:
            print(f"⚠️  No text extracted for resume {resume_id} — marking failed")
            update_resume_failed(resume_id)
            _publish_status(resume_id, "failed")
            return

        print(f"🤖 [Task {self.request.id}] AI parsing resume {resume_id} ({len(raw_text)} chars)...")
        parsed_data = parse_resume(raw_text)

        update_resume_parsed(resume_id, raw_text, parsed_data)
        candidate_name = parsed_data.get("name", "Unknown")
        print(f"✅ Resume {resume_id} parsed successfully: {candidate_name}")
        _publish_status(resume_id, "success", candidate_name)

    except SoftTimeLimitExceeded:
        print(f"⏰ Timeout parsing resume {resume_id} — marking failed")
        update_resume_failed(resume_id)
        _publish_status(resume_id, "failed")

    except Exception as exc:
        attempt = self.request.retries + 1
        max_attempts = self.max_retries + 1
        print(f"❌ Parse failed for resume {resume_id} (attempt {attempt}/{max_attempts}): {exc}")

        if self.request.retries >= self.max_retries:
            update_resume_failed(resume_id)
            _publish_status(resume_id, "failed")
            return

        # Exponential backoff: 30s → 60s → 120s
        backoff = 30 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=backoff)

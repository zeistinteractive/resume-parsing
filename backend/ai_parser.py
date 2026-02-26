"""
AI-powered resume parsing using Gemini API.
Extracts structured data from raw resume text.
"""
import json
import re
import os
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_PROMPT = """You are a resume parser. Extract structured data from the resume text and return ONLY valid JSON. No explanation, no markdown, no backticks."""

USER_PROMPT_TEMPLATE = """Parse this resume and return a JSON object with exactly these fields:

{{
  "name": "Full name of the candidate",
  "email": "email address or empty string",
  "phone": "phone number or empty string",
  "summary": "brief professional summary or empty string",
  "current_title": "Most recent job title, e.g. 'Senior Software Engineer'. Empty string if no experience.",
  "location": "City and country extracted from the resume, e.g. 'Pune, India' or 'New York, USA'. Empty string if not mentioned.",
  "experience_years": 0,
  "notice_period": "One of exactly: Immediate | 15 days | 30 days | 60 days | 90 days | >90 days | Not mentioned",
  "education_level": "One of exactly: High School | Diploma | Bachelor's | Master's | MBA | PhD | Other",
  "skills": ["skill1", "skill2", "skill3"],
  "experience": [
    {{
      "company": "Company name",
      "title": "Job title",
      "dates": "Date range e.g. Jan 2020 - Present",
      "description": "Brief role description"
    }}
  ],
  "education": [
    {{
      "institution": "University/School name",
      "degree": "Degree name",
      "dates": "Year or date range"
    }}
  ]
}}

Rules:
- skills must be a flat array of strings (technologies, tools, languages, frameworks)
- current_title must be the title from the most recent / current job only
- experience_years must be a single integer: total years of professional work experience.
  Calculate by summing all non-overlapping work periods. If only a graduation year is present
  and no work history, set to 0. Round down to the nearest whole year.
- notice_period: use exactly one of the allowed values listed above. If the resume says
  "immediately available" use "Immediate". If not mentioned at all, use "Not mentioned".
- education_level: use the highest degree attained. Bachelor's covers B.Tech/B.E./B.Sc/BA/BCA.
  Master's covers M.Tech/M.E./M.Sc/MS (non-MBA). MBA is its own category. PhD covers doctoral degrees.
- Return ONLY the JSON object, nothing else
- If a field is missing from the resume, use empty string, 0, or "Not mentioned" as appropriate

Resume text:
{raw_text}"""


def parse_resume(raw_text: str) -> dict:
    """
    Send raw resume text to Gemini and return structured parsed data.
    Returns a dict with all fields including the five new structured ones:
    current_title, location, experience_years, notice_period, education_level.
    """
    if not raw_text or len(raw_text.strip()) < 50:
        return _empty_result()

    # Truncate very long resumes to avoid token limits
    truncated = raw_text[:8000] if len(raw_text) > 8000 else raw_text

    prompt = USER_PROMPT_TEMPLATE.format(raw_text=truncated)

    try:
        model = genai.GenerativeModel(
            model_name="gemini-2.0-flash",
            system_instruction=SYSTEM_PROMPT,
        )

        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Strip any accidental markdown fences
        response_text = re.sub(r'^```json\s*', '', response_text)
        response_text = re.sub(r'^```\s*', '', response_text)
        response_text = re.sub(r'\s*```$', '', response_text)

        parsed = json.loads(response_text)
        return _normalize(parsed)

    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
        print(f"Response was: {response_text[:200]}")
        return _empty_result()
    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        raise


# ── Allowed values for constrained fields ─────────────────────────────────────

_NOTICE_PERIODS = frozenset({
    "Immediate", "15 days", "30 days", "60 days", "90 days", ">90 days", "Not mentioned"
})

_EDUCATION_LEVELS = frozenset({
    "High School", "Diploma", "Bachelor's", "Master's", "MBA", "PhD", "Other"
})


def _normalize(data: dict) -> dict:
    """Ensure all expected fields exist with correct types."""
    notice   = str(data.get("notice_period") or "Not mentioned").strip()
    education = str(data.get("education_level") or "Other").strip()

    # Clamp to allowed values so the dropdown filter always works
    if notice not in _NOTICE_PERIODS:
        notice = "Not mentioned"
    if education not in _EDUCATION_LEVELS:
        education = "Other"

    # experience_years must be a non-negative integer
    try:
        exp_years = max(0, int(data.get("experience_years") or 0))
    except (TypeError, ValueError):
        exp_years = 0

    return {
        "name":             str(data.get("name") or ""),
        "email":            str(data.get("email") or ""),
        "phone":            str(data.get("phone") or ""),
        "summary":          str(data.get("summary") or ""),
        "current_title":    str(data.get("current_title") or ""),
        "location":         str(data.get("location") or ""),
        "experience_years": exp_years,
        "notice_period":    notice,
        "education_level":  education,
        "skills": [str(s) for s in (data.get("skills") or []) if s],
        "experience": [
            {
                "company":     str(e.get("company") or ""),
                "title":       str(e.get("title") or ""),
                "dates":       str(e.get("dates") or ""),
                "description": str(e.get("description") or ""),
            }
            for e in (data.get("experience") or [])
        ],
        "education": [
            {
                "institution": str(e.get("institution") or ""),
                "degree":      str(e.get("degree") or ""),
                "dates":       str(e.get("dates") or ""),
            }
            for e in (data.get("education") or [])
        ],
    }


def _empty_result() -> dict:
    return {
        "name": "", "email": "", "phone": "", "summary": "",
        "current_title": "", "location": "",
        "experience_years": 0,
        "notice_period": "Not mentioned",
        "education_level": "Other",
        "skills": [], "experience": [], "education": [],
    }

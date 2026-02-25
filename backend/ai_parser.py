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
- Skills must be a flat array of strings (technologies, tools, languages)
- Return ONLY the JSON object, nothing else
- If a field is missing from the resume, use empty string or empty array

Resume text:
{raw_text}"""


def parse_resume(raw_text: str) -> dict:
    """
    Send raw resume text to Gemini and return structured parsed data.
    Returns a dict with name, email, phone, summary, skills, experience, education.
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


def _normalize(data: dict) -> dict:
    """Ensure all expected fields exist with correct types."""
    return {
        "name": str(data.get("name") or ""),
        "email": str(data.get("email") or ""),
        "phone": str(data.get("phone") or ""),
        "summary": str(data.get("summary") or ""),
        "skills": [str(s) for s in (data.get("skills") or []) if s],
        "experience": [
            {
                "company": str(e.get("company") or ""),
                "title": str(e.get("title") or ""),
                "dates": str(e.get("dates") or ""),
                "description": str(e.get("description") or ""),
            }
            for e in (data.get("experience") or [])
        ],
        "education": [
            {
                "institution": str(e.get("institution") or ""),
                "degree": str(e.get("degree") or ""),
                "dates": str(e.get("dates") or ""),
            }
            for e in (data.get("education") or [])
        ],
    }


def _empty_result() -> dict:
    return {
        "name": "", "email": "", "phone": "", "summary": "",
        "skills": [], "experience": [], "education": []
    }

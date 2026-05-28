"""
AI Engine — powered by Claude (claude-sonnet-4-20250514).
Handles:
  1. Resume tailoring (rephrase/reorder only — no fabrication)
  2. Match scoring
  3. Cover letter generation
  4. Application question extraction + prefill
  5. Resume text extraction from uploaded file text
"""

import os
import json
import logging
import anthropic

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
MODEL = "claude-sonnet-4-5"


def _call(system: str, user: str, max_tokens: int = 2000) -> str:
    """Single Claude API call, returns text content."""
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        raise


def _call_json(system: str, user: str, max_tokens: int = 2000) -> dict:
    """Claude call that expects JSON back. Returns parsed dict."""
    raw = _call(system, user, max_tokens)
    # Strip markdown fences if present
    clean = raw.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        clean = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse failed: {e}\nRaw: {raw[:500]}")
        return {}


# ── 1. Score & Quick Check ─────────────────────────────────────────────────────

def score_match(resume_text: str, job_description: str, job_title: str) -> int:
    """
    Return a match score 0–100.
    Used as a quick pre-filter before spending more tokens on full tailoring.
    """
    system = (
        "You are an ATS and hiring expert. "
        "Given a resume and a job description, return ONLY a JSON object like: "
        '{"score": 72, "reason": "one sentence reason"} '
        "Score 0-100 based on skills overlap, seniority match, and domain relevance. "
        "Be honest — do not inflate the score."
    )
    user = (
        f"JOB TITLE: {job_title}\n\n"
        f"JOB DESCRIPTION:\n{job_description[:3000]}\n\n"
        f"RESUME:\n{resume_text[:3000]}"
    )
    result = _call_json(system, user, max_tokens=200)
    score = result.get("score", 0)
    return max(0, min(100, int(score)))


# ── 2. Full AI Processing ──────────────────────────────────────────────────────

def process_job(resume_text: str, job: dict) -> dict:
    """
    Full AI pipeline for one job.
    Returns dict with: tailored_resume, match_score, cover_letter, questions_qa
    """
    jd = job.get("description", "")
    title = job.get("title", "")
    company = job.get("company", "")

    if not jd:
        jd = f"Job Title: {title} at {company}. India-based role."

    # Step 1: Score
    score = score_match(resume_text, jd, title)
    logger.info(f"Match score for '{title}' at {company}: {score}")

    # Step 2: Tailored resume sections
    tailored = tailor_resume(resume_text, jd, title, company)

    # Step 3: Cover letter
    cover = generate_cover_letter(resume_text, jd, title, company)

    # Step 4: Application questions
    questions_qa = extract_and_answer_questions(jd, resume_text, title, company)

    return {
        "match_score": score,
        "tailored_resume": tailored,
        "cover_letter": cover,
        "questions_qa": questions_qa,
    }


# ── 3. Resume Tailoring ────────────────────────────────────────────────────────

def tailor_resume(resume_text: str, job_description: str, job_title: str, company: str) -> dict:
    """
    Returns a structured dict of resume sections, tailored to the JD.
    STRICT RULE: Only rephrases/reorders existing content. Zero fabrication.
    """
    system = """You are an expert ATS resume writer. Your ONLY job is to rephrase and reorder the candidate's existing experience to best match the job description.

ABSOLUTE RULES — never break these:
1. DO NOT add any experience, skills, tools, or achievements that are not explicitly in the resume.
2. DO NOT invent metrics, numbers, or outcomes not already present.
3. DO NOT change job titles, company names, or dates.
4. You MAY rephrase bullet points using keywords from the JD, as long as the meaning stays true to the original.
5. You MAY reorder bullet points to surface the most relevant ones first.
6. You MAY use terminology from the JD to describe existing skills (e.g. if resume says "managed client relationships" and JD says "customer success", you can say "drove customer success through managing client relationships").

Return ONLY a JSON object with this structure:
{
  "summary": "2-3 sentence professional summary tailored to this role",
  "experience": [
    {
      "company": "Company name",
      "title": "Job title",
      "dates": "Date range",
      "bullets": ["bullet 1", "bullet 2", ...]
    }
  ],
  "skills": ["skill1", "skill2", ...],
  "education": [
    {
      "institution": "Name",
      "degree": "Degree",
      "year": "Year"
    }
  ],
  "certifications": ["cert1", "cert2"]
}"""

    user = (
        f"TARGET ROLE: {job_title} at {company}\n\n"
        f"JOB DESCRIPTION:\n{job_description[:3500]}\n\n"
        f"MY RESUME:\n{resume_text[:3500]}\n\n"
        "Tailor my resume for this role. Remember: only rephrase existing content, never add new experience."
    )

    result = _call_json(system, user, max_tokens=3000)

    # Validate — if fields are missing, return safe defaults
    if not result.get("experience"):
        logger.warning("Tailored resume missing experience — falling back to basic parse")
        result = _basic_resume_parse(resume_text)

    return result


def _basic_resume_parse(resume_text: str) -> dict:
    """Emergency fallback: ask Claude to just structure the resume as-is."""
    system = (
        "Parse this resume into a JSON object with keys: "
        "summary, experience (array of {company, title, dates, bullets}), "
        "skills (array), education (array of {institution, degree, year}), certifications (array). "
        "Return only valid JSON."
    )
    return _call_json(system, resume_text[:4000], max_tokens=2500)


# ── 4. Cover Letter ────────────────────────────────────────────────────────────

def generate_cover_letter(resume_text: str, job_description: str, job_title: str, company: str) -> str:
    """
    Generate a cover letter under 200 words.
    Semi-formal, slightly imperfect, human tone.
    """
    system = """You write cover letters that sound like a real person wrote them — not a robot.

Rules:
- Under 200 words. Hard limit.
- Semi-formal tone. Not stiff corporate language.
- Slightly imperfect English is fine — contractions, natural phrasing, occasional informality.
- Must sound human. Avoid buzzword-heavy perfection.
- Connect 2-3 specific things from the person's actual experience to the role.
- Do NOT fabricate any experience or skills not in the resume.
- End with a genuine, brief closing — not a cliche.
- No "I am writing to express my interest" style openers."""

    user = (
        f"Write a cover letter for: {job_title} at {company}\n\n"
        f"JOB DESCRIPTION (key points):\n{job_description[:2000]}\n\n"
        f"MY EXPERIENCE:\n{resume_text[:2500]}"
    )

    return _call(system, user, max_tokens=400)


# ── 5. Application Questions ───────────────────────────────────────────────────

def extract_and_answer_questions(job_description: str, resume_text: str, job_title: str, company: str) -> list:
    """
    Extract any application questions from the JD and pre-fill answers.
    Returns list of {question, answer} dicts.
    If no questions found, returns empty list.
    """
    system = (
        "Look at this job description and identify any explicit application questions "
        "(e.g. 'Why do you want to work here?', 'Describe your experience with X', etc.). "
        "Then draft honest answers based ONLY on the candidate's resume. "
        "If no questions are found, return an empty array. "
        "Return JSON: [{\"question\": \"...\", \"answer\": \"...\"}]"
    )
    user = (
        f"JOB: {job_title} at {company}\n\n"
        f"JOB DESCRIPTION:\n{job_description[:3000]}\n\n"
        f"RESUME:\n{resume_text[:2500]}"
    )
    result = _call(system, user, max_tokens=1500)
    # Try to parse as JSON array
    clean = result.strip()
    if clean.startswith("```"):
        lines = clean.split("\n")
        clean = "\n".join(lines[1:-1])
    try:
        parsed = json.loads(clean)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        pass
    return []


# ── 6. Resume Text Extraction ──────────────────────────────────────────────────

def extract_resume_text_from_raw(raw_text: str) -> str:
    """
    Clean up raw PDF/docx-extracted text into structured plain text.
    Called once when a new resume is uploaded.
    """
    system = (
        "You are given raw text extracted from a resume PDF or Word doc. "
        "It may have garbled formatting. Clean it up into well-structured plain text. "
        "Preserve all information exactly — do not add or remove anything. "
        "Format: sections with headers (SUMMARY, EXPERIENCE, SKILLS, EDUCATION, CERTIFICATIONS). "
        "Return only the cleaned resume text, no commentary."
    )
    return _call(system, raw_text[:5000], max_tokens=3000)

"""
ATS-clean PDF resume generator.
Single-column, plain formatting — maximum parser compatibility.
Uses reportlab (pure Python, no system dependencies).
"""

import os
import logging
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, ListFlowable, ListItem
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

logger = logging.getLogger(__name__)

# ── Colours (minimal — ATS safe) ──────────────────────────────────────────────
BLACK = colors.HexColor("#000000")
DARK_GREY = colors.HexColor("#2d2d2d")
MID_GREY = colors.HexColor("#555555")
LIGHT_GREY = colors.HexColor("#888888")
RULE_COLOUR = colors.HexColor("#cccccc")

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm


def _styles():
    base = getSampleStyleSheet()

    name_style = ParagraphStyle(
        "CandidateName",
        parent=base["Normal"],
        fontSize=20,
        leading=24,
        textColor=DARK_GREY,
        alignment=TA_LEFT,
        fontName="Helvetica-Bold",
        spaceAfter=2,
    )
    contact_style = ParagraphStyle(
        "Contact",
        parent=base["Normal"],
        fontSize=9,
        leading=13,
        textColor=MID_GREY,
        alignment=TA_LEFT,
        spaceAfter=6,
    )
    section_style = ParagraphStyle(
        "SectionHeader",
        parent=base["Normal"],
        fontSize=10,
        leading=14,
        textColor=DARK_GREY,
        fontName="Helvetica-Bold",
        spaceBefore=10,
        spaceAfter=2,
        textTransform="uppercase",
        letterSpacing=1,
    )
    job_title_style = ParagraphStyle(
        "JobTitle",
        parent=base["Normal"],
        fontSize=10,
        leading=14,
        textColor=DARK_GREY,
        fontName="Helvetica-Bold",
        spaceBefore=6,
        spaceAfter=0,
    )
    job_meta_style = ParagraphStyle(
        "JobMeta",
        parent=base["Normal"],
        fontSize=9,
        leading=12,
        textColor=LIGHT_GREY,
        spaceAfter=2,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=base["Normal"],
        fontSize=9.5,
        leading=14,
        textColor=DARK_GREY,
        spaceAfter=2,
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        parent=body_style,
        leftIndent=12,
        bulletIndent=0,
        spaceAfter=1,
    )
    summary_style = ParagraphStyle(
        "Summary",
        parent=body_style,
        fontSize=9.5,
        leading=14,
        textColor=MID_GREY,
        spaceAfter=4,
    )
    return {
        "name": name_style,
        "contact": contact_style,
        "section": section_style,
        "job_title": job_title_style,
        "job_meta": job_meta_style,
        "body": body_style,
        "bullet": bullet_style,
        "summary": summary_style,
    }


def _rule():
    return HRFlowable(width="100%", thickness=0.5, color=RULE_COLOUR, spaceAfter=4, spaceBefore=2)


def generate_ats_resume(resume_data: dict, candidate_info: dict, output_path: str) -> str:
    """
    Generate an ATS-clean PDF resume.

    Args:
        resume_data: dict from claude_engine.tailor_resume()
            Keys: summary, experience, skills, education, certifications
        candidate_info: dict with name, email, phone, linkedin (extracted from resume text or config)
        output_path: full path where PDF should be saved

    Returns:
        output_path on success
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"Resume - {candidate_info.get('name', 'Candidate')}",
    )

    S = _styles()
    story = []

    # ── Header ─────────────────────────────────────────────────────────────────
    name = candidate_info.get("name", "")
    if name:
        story.append(Paragraph(name, S["name"]))

    contact_parts = []
    if candidate_info.get("email"):
        contact_parts.append(candidate_info["email"])
    if candidate_info.get("phone"):
        contact_parts.append(candidate_info["phone"])
    if candidate_info.get("location"):
        contact_parts.append(candidate_info["location"])
    if candidate_info.get("linkedin"):
        contact_parts.append(candidate_info["linkedin"])
    if contact_parts:
        story.append(Paragraph("  |  ".join(contact_parts), S["contact"]))

    story.append(_rule())

    # ── Summary ────────────────────────────────────────────────────────────────
    summary = resume_data.get("summary", "")
    if summary:
        story.append(Paragraph("PROFESSIONAL SUMMARY", S["section"]))
        story.append(_rule())
        story.append(Paragraph(summary, S["summary"]))
        story.append(Spacer(1, 4))

    # ── Experience ─────────────────────────────────────────────────────────────
    experience = resume_data.get("experience", [])
    if experience:
        story.append(Paragraph("EXPERIENCE", S["section"]))
        story.append(_rule())
        for exp in experience:
            # Job title line
            title_company = f"{exp.get('title', '')}  —  {exp.get('company', '')}"
            story.append(Paragraph(title_company, S["job_title"]))
            # Dates
            if exp.get("dates"):
                story.append(Paragraph(exp["dates"], S["job_meta"]))
            # Bullets
            for bullet in exp.get("bullets", []):
                if bullet.strip():
                    story.append(Paragraph(f"• {bullet.strip()}", S["bullet"]))
            story.append(Spacer(1, 4))

    # ── Skills ─────────────────────────────────────────────────────────────────
    skills = resume_data.get("skills", [])
    if skills:
        story.append(Paragraph("SKILLS", S["section"]))
        story.append(_rule())
        skills_text = "  •  ".join(skills)
        story.append(Paragraph(skills_text, S["body"]))
        story.append(Spacer(1, 4))

    # ── Education ──────────────────────────────────────────────────────────────
    education = resume_data.get("education", [])
    if education:
        story.append(Paragraph("EDUCATION", S["section"]))
        story.append(_rule())
        for edu in education:
            line = f"{edu.get('degree', '')}  —  {edu.get('institution', '')}"
            if edu.get("year"):
                line += f"  ({edu['year']})"
            story.append(Paragraph(line, S["body"]))

    # ── Certifications ─────────────────────────────────────────────────────────
    certs = resume_data.get("certifications", [])
    if certs:
        story.append(Spacer(1, 4))
        story.append(Paragraph("CERTIFICATIONS", S["section"]))
        story.append(_rule())
        for cert in certs:
            if cert.strip():
                story.append(Paragraph(f"• {cert.strip()}", S["bullet"]))

    doc.build(story)
    logger.info(f"ATS resume PDF saved: {output_path}")
    return output_path


def extract_candidate_info(resume_text: str) -> dict:
    """
    Quick heuristic extraction of name, email, phone, linkedin from resume text.
    Used to populate the PDF header.
    """
    import re
    info = {
        "name": "",
        "email": "",
        "phone": "",
        "linkedin": "",
        "location": "India",
    }

    lines = [l.strip() for l in resume_text.split("\n") if l.strip()]

    # Email
    email_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", resume_text)
    if email_match:
        info["email"] = email_match.group()

    # Phone — Indian numbers
    phone_match = re.search(r"(\+91[\s\-]?)?[6-9]\d{9}", resume_text)
    if phone_match:
        info["phone"] = phone_match.group()

    # LinkedIn
    linkedin_match = re.search(r"linkedin\.com/in/[\w\-]+", resume_text, re.IGNORECASE)
    if linkedin_match:
        info["linkedin"] = "linkedin.com/in/" + linkedin_match.group().split("/in/")[-1]

    # Name — heuristic: first non-empty line that looks like a name (2-4 words, no numbers)
    for line in lines[:5]:
        words = line.split()
        if 2 <= len(words) <= 4 and all(w.replace("-", "").isalpha() for w in words):
            info["name"] = line
            break

    return info

"""
main.py — Daily job tracker orchestrator.
Writes to BOTH AITable (data store) and EZSite (dashboard display).
"""

import os
import sys
import logging
import tempfile
from datetime import date
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")

from utils.aitable_client import (
    get_active_job_titles,
    get_active_company_urls as aitable_get_company_urls,
    get_active_resume,
    get_seen_job_hashes,
    mark_job_seen,
    save_job_posting as aitable_save_job,
    save_application as aitable_save_application,
    upload_attachment,
    update_company_url_last_scraped as aitable_update_scraped,
)
from utils.ezsite_client import (
    save_job_posting as ezsite_save_job,
    save_application as ezsite_save_application,
    update_company_url_last_scraped as ezsite_update_scraped,
    get_active_company_urls as ezsite_get_company_urls,
)
from scrapers import scrape_all_boards, scrape_custom_urls
from ai_engine.claude_engine import process_job, score_match
from generators.pdf_resume import generate_ats_resume, extract_candidate_info
from generators.word_qa import generate_qa_document

MIN_SCORE_TO_PROCESS = 40
SCORE_TO_SKIP = 25
DST_APPLICATIONS = os.environ["DST_APPLICATIONS"]


def run():
    logger.info("=" * 60)
    logger.info(f"Job Tracker — Run started: {date.today()}")
    logger.info("=" * 60)

    # ── Step 1: Load config ────────────────────────────────────────────────────
    logger.info("Loading config from AITable...")
    titles = get_active_job_titles()
    resume_text = get_active_resume()
    seen_hashes = get_seen_job_hashes()

    # Company URLs — try EZSite first (user may add via dashboard),
    # fall back to AITable
    company_urls = ezsite_get_company_urls()
    if not company_urls:
        company_urls = aitable_get_company_urls()
        logger.info(f"Using AITable company URLs: {len(company_urls)}")
    else:
        logger.info(f"Using EZSite company URLs: {len(company_urls)}")

    logger.info(f"Active job titles: {len(titles)}")
    logger.info(f"Already seen jobs: {len(seen_hashes)}")

    if not resume_text:
        logger.error("No active resume found in AITable!")
        sys.exit(1)

    if not titles:
        logger.error("No active job titles found in AITable!")
        sys.exit(1)

    candidate_info = extract_candidate_info(resume_text)
    logger.info(f"Resume loaded for: {candidate_info.get('name', 'Unknown')}")

    # ── Step 2: Scrape ─────────────────────────────────────────────────────────
    logger.info("Starting scrape of job boards...")
    board_jobs = scrape_all_boards(titles, seen_hashes)

    logger.info("Scraping custom company URLs...")
    custom_jobs = scrape_custom_urls(company_urls, titles, seen_hashes)

    all_new_jobs = board_jobs + custom_jobs
    logger.info(f"Total new jobs to process: {len(all_new_jobs)}")

    if not all_new_jobs:
        logger.info("No new jobs found this run. Exiting.")
        return

    # ── Step 3: Process each job ───────────────────────────────────────────────
    processed = 0
    skipped_low_score = 0
    errors = 0

    for i, job in enumerate(all_new_jobs, 1):
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        logger.info(f"[{i}/{len(all_new_jobs)}] Processing: {title} @ {company}")

        try:
            # Quick score
            quick_score = score_match(resume_text, job.get("description", ""), title)
            job["match_score"] = quick_score
            job["date_found"] = str(date.today())

            # Mark seen immediately
            mark_job_seen(job["job_url"])

            if quick_score < SCORE_TO_SKIP:
                logger.info(f"  Score {quick_score} — below threshold, skipping.")
                skipped_low_score += 1
                # Save to both so it appears in dashboard
                aitable_save_job(job)
                ezsite_save_job(job)
                continue

            # Save to both databases
            aitable_save_job(job)
            ezsite_save_job(job)

            if quick_score < MIN_SCORE_TO_PROCESS:
                logger.info(f"  Score {quick_score} — saved but not fully processed.")
                continue

            # ── Full AI pipeline ───────────────────────────────────────────────
            logger.info(f"  Score {quick_score} — running full AI pipeline...")
            ai_result = process_job(resume_text, job)

            match_score = ai_result["match_score"]
            tailored_resume = ai_result["tailored_resume"]
            cover_letter = ai_result["cover_letter"]
            questions_qa = ai_result["questions_qa"]

            logger.info(f"  Final match score: {match_score}")

            # ── Generate files ─────────────────────────────────────────────────
            with tempfile.TemporaryDirectory() as tmpdir:
                safe_company = "".join(c for c in company if c.isalnum() or c in " _-")[:30]
                safe_title = "".join(c for c in title if c.isalnum() or c in " _-")[:30]
                date_str = str(date.today())

                pdf_path = os.path.join(tmpdir, f"Resume_{safe_company}_{date_str}.pdf")
                docx_path = os.path.join(tmpdir, f"QA_{safe_company}_{date_str}.docx")

                generate_ats_resume(tailored_resume, candidate_info, pdf_path)
                generate_qa_document(
                    questions_qa=questions_qa,
                    job_title=title,
                    company=company,
                    job_url=job["job_url"],
                    cover_letter=cover_letter,
                    output_path=docx_path,
                )

                # ── Save to AITable with attachments ───────────────────────────
                aitable_app_id = aitable_save_application({
                    "job_url": job["job_url"],
                    "company": company,
                    "job_title": title,
                    "match_score": match_score,
                    "cover_letter": cover_letter,
                    "applied_date": date_str,
                })
                if aitable_app_id:
                    try:
                        upload_attachment(DST_APPLICATIONS, aitable_app_id, "resume_pdf", pdf_path)
                        logger.info(f"  ✓ AITable: Resume PDF uploaded")
                    except Exception as e:
                        logger.error(f"  AITable PDF upload failed: {e}")
                    try:
                        upload_attachment(DST_APPLICATIONS, aitable_app_id, "questions_doc", docx_path)
                        logger.info(f"  ✓ AITable: Q&A doc uploaded")
                    except Exception as e:
                        logger.error(f"  AITable Word doc upload failed: {e}")

                # ── Save to EZSite (for dashboard display) ─────────────────────
                # EZSite stores URLs as text — files are stored in AITable,
                # we save the AITable record reference as the download URL
                ezsite_save_application({
                    "job_url": job["job_url"],
                    "company": company,
                    "job_title": title,
                    "match_score": match_score,
                    "cover_letter": cover_letter,
                    "applied_date": date_str,
                    "resume_url": "",       # Will be updated once AITable upload confirmed
                    "questions_doc_url": "",
                })
                logger.info(f"  ✓ EZSite: Application saved")

            # Update company URL last scraped
            if job.get("_company_url_record_id"):
                aitable_update_scraped(job["_company_url_record_id"])
            if job.get("ezsite_record_id"):
                ezsite_update_scraped(job["ezsite_record_id"])

            processed += 1
            logger.info(f"  ✓ Done: {title} @ {company} | Score: {match_score}")

        except Exception as e:
            logger.error(f"  ✗ Failed: {title} @ {company} | Error: {e}")
            errors += 1

    # ── Summary ────────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info(f"Run complete.")
    logger.info(f"  New jobs found:       {len(all_new_jobs)}")
    logger.info(f"  Fully processed:      {processed}")
    logger.info(f"  Skipped (low score):  {skipped_low_score}")
    logger.info(f"  Errors:               {errors}")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()


def generate_and_push_dashboard():
    """Generate HTML dashboard and commit to GitHub Pages."""
    try:
        from dashboard.generator import generate_dashboard
        generate_dashboard()
        logger.info("Dashboard HTML generated successfully")
    except Exception as e:
        logger.error(f"Dashboard generation failed: {e}")

"""
main.py — Daily job tracker orchestrator.
This is what GitHub Actions runs twice a day.

Flow:
1. Load config from AITable (titles, resume, company URLs)
2. Scrape all boards for new jobs
3. Deduplicate
4. For each new job: run AI pipeline
5. Generate PDF resume + Word Q&A doc
6. Upload files to AITable
7. Write records to AITable
"""

import os
import sys
import logging
import tempfile
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

# Load .env for local runs (GitHub Actions uses Secrets instead)
load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")

# ── Imports (after env loaded) ────────────────────────────────────────────────
from utils.aitable_client import (
    get_active_job_titles,
    get_active_company_urls,
    get_active_resume,
    get_seen_job_hashes,
    mark_job_seen,
    save_job_posting,
    save_application,
    upload_attachment,
    update_company_url_last_scraped,
)
from scrapers import scrape_all_boards, scrape_custom_urls
from ai_engine.claude_engine import process_job, score_match
from generators.pdf_resume import generate_ats_resume, extract_candidate_info
from generators.word_qa import generate_qa_document

# ── Config ────────────────────────────────────────────────────────────────────
MIN_SCORE_TO_PROCESS = 40   # Jobs below this score are saved but not fully processed
SCORE_TO_SKIP = 25          # Jobs below this score are skipped entirely
DST_APPLICATIONS = os.environ["DST_APPLICATIONS"]
DST_JOB_POSTINGS = os.environ["DST_JOB_POSTINGS"]


def run():
    logger.info("=" * 60)
    logger.info(f"Job Tracker — Run started: {date.today()}")
    logger.info("=" * 60)

    # ── Step 1: Load from AITable ──────────────────────────────────────────────
    logger.info("Loading config from AITable...")
    titles = get_active_job_titles()
    company_urls = get_active_company_urls()
    resume_text = get_active_resume()
    seen_hashes = get_seen_job_hashes()

    logger.info(f"Active job titles: {len(titles)}")
    logger.info(f"Active company URLs: {len(company_urls)}")
    logger.info(f"Already seen jobs: {len(seen_hashes)}")

    if not resume_text:
        logger.error("No active resume found in AITable! Upload your resume and mark is_active = true.")
        sys.exit(1)

    if not titles:
        logger.error("No active job titles found in AITable!")
        sys.exit(1)

    # Candidate info for PDF header
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
            # Quick score check before spending full AI tokens
            quick_score = score_match(resume_text, job.get("description", ""), title)
            job["match_score"] = quick_score

            # Mark as seen immediately so it's not reprocessed on next run
            mark_job_seen(job["job_url"])

            if quick_score < SCORE_TO_SKIP:
                logger.info(f"  Score {quick_score} — below threshold, skipping.")
                skipped_low_score += 1
                # Still save to job_postings so you can see it if you want
                save_job_posting({**job, "match_score": quick_score})
                continue

            # Save to job_postings
            posting_record_id = save_job_posting(job)

            if quick_score < MIN_SCORE_TO_PROCESS:
                logger.info(f"  Score {quick_score} — saved but not fully processed (below {MIN_SCORE_TO_PROCESS}).")
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

                pdf_name = f"Resume_{safe_company}_{safe_title}_{date_str}.pdf"
                docx_name = f"QA_{safe_company}_{safe_title}_{date_str}.docx"
                pdf_path = os.path.join(tmpdir, pdf_name)
                docx_path = os.path.join(tmpdir, docx_name)

                # Generate PDF
                generate_ats_resume(tailored_resume, candidate_info, pdf_path)

                # Generate Word doc
                generate_qa_document(
                    questions_qa=questions_qa,
                    job_title=title,
                    company=company,
                    job_url=job["job_url"],
                    cover_letter=cover_letter,
                    output_path=docx_path,
                )

                # ── Save application record ────────────────────────────────────
                app_record_id = save_application({
                    "job_url": job["job_url"],
                    "company": company,
                    "job_title": title,
                    "match_score": match_score,
                    "cover_letter": cover_letter,
                })

                # ── Upload attachments ─────────────────────────────────────────
                if app_record_id:
                    try:
                        upload_attachment(DST_APPLICATIONS, app_record_id, "resume_pdf", pdf_path)
                        logger.info(f"  ✓ Resume PDF uploaded")
                    except Exception as e:
                        logger.error(f"  PDF upload failed: {e}")

                    try:
                        upload_attachment(DST_APPLICATIONS, app_record_id, "questions_doc", docx_path)
                        logger.info(f"  ✓ Q&A doc uploaded")
                    except Exception as e:
                        logger.error(f"  Word doc upload failed: {e}")

            # Update company URL last_scraped if applicable
            if job.get("_company_url_record_id"):
                update_company_url_last_scraped(job["_company_url_record_id"])

            processed += 1
            logger.info(f"  ✓ Done: {title} @ {company} | Score: {match_score}")

        except Exception as e:
            logger.error(f"  ✗ Failed to process job: {title} @ {company} | Error: {e}")
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

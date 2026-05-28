"""
EZSite API client.
Writes job postings and applications to EZSite database
so the dashboard displays live data.

Table IDs:
  job_postings  → 83374
  applications  → 83375
  company_urls  → 83376
"""

import os
import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

EZSITE_BASE = "https://usapi.hottask.com/autodev/CustomTableValue"
EZSITE_RANDOM_CODE = os.environ.get("EZSITE_RANDOM_CODE", "7iivmcizgxdr")

TABLE_JOB_POSTINGS = os.environ.get("EZSITE_TABLE_JOB_POSTINGS", "83374")
TABLE_APPLICATIONS = os.environ.get("EZSITE_TABLE_APPLICATIONS", "83375")
TABLE_COMPANY_URLS = os.environ.get("EZSITE_TABLE_COMPANY_URLS", "83376")


def _headers():
    return {
        "Authorization": os.environ["EZSITE_API_TOKEN"],
        "Content-Type": "application/json",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _post(table_id: str, payload: dict) -> dict:
    url = f"{EZSITE_BASE}/Create/{EZSITE_RANDOM_CODE}/{table_id}"
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _patch(table_id: str, payload: dict) -> dict:
    url = f"{EZSITE_BASE}/UD/{EZSITE_RANDOM_CODE}/{table_id}"
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _get(table_id: str, params: dict = None) -> dict:
    url = f"{EZSITE_BASE}/GetTableDataList/{EZSITE_RANDOM_CODE}/{table_id}"
    r = requests.get(url, headers=_headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def save_job_posting(job: dict) -> int:
    """Write a job posting to EZSite job_postings table."""
    try:
        resp = _post(TABLE_JOB_POSTINGS, {"create": {
            "job_title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", "India"),
            "job_board": job.get("job_board", ""),
            "job_url": job.get("job_url", ""),
            "description": job.get("description", "")[:5000],
            "date_found": str(job.get("date_found", "")),
            "status": "new",
            "match_score": job.get("match_score", 0),
        }})
        if resp.get("Success"):
            record_id = resp.get("Data")
            logger.info(f"EZSite job_postings saved → ID: {record_id}")
            return record_id
        else:
            logger.error(f"EZSite save_job_posting failed: {resp.get('Message')}")
            return None
    except Exception as e:
        logger.error(f"EZSite save_job_posting error: {e}")
        return None


def save_application(app: dict) -> int:
    """Write an application to EZSite applications table."""
    try:
        resp = _post(TABLE_APPLICATIONS, {"create": {
            "job_ref": app.get("job_url", ""),
            "company": app.get("company", ""),
            "job_title": app.get("job_title", ""),
            "applied_date": str(app.get("applied_date", "")),
            "match_score": app.get("match_score", 0),
            "cover_letter": app.get("cover_letter", ""),
            "job_url": app.get("job_url", ""),
            "status": "pending",
            "resume_url": app.get("resume_url", ""),
            "questions_doc_url": app.get("questions_doc_url", ""),
        }})
        if resp.get("Success"):
            record_id = resp.get("Data")
            logger.info(f"EZSite applications saved → ID: {record_id}")
            return record_id
        else:
            logger.error(f"EZSite save_application failed: {resp.get('Message')}")
            return None
    except Exception as e:
        logger.error(f"EZSite save_application error: {e}")
        return None


def update_job_status(record_id: int, status: str):
    """Update job posting status in EZSite."""
    try:
        _patch(TABLE_JOB_POSTINGS, {"update": {
            "id": record_id,
            "status": status,
        }})
        logger.info(f"EZSite job {record_id} status → {status}")
    except Exception as e:
        logger.error(f"EZSite update_job_status error: {e}")


def update_company_url_last_scraped(ezsite_record_id: int):
    """Update last_scraped date on a company_urls record."""
    try:
        from datetime import date
        _patch(TABLE_COMPANY_URLS, {"update": {
            "id": ezsite_record_id,
            "last_scraped": str(date.today()),
        }})
    except Exception as e:
        logger.error(f"EZSite update_company_url_last_scraped error: {e}")


def get_active_company_urls() -> list:
    """Read company_urls from EZSite where active = true."""
    try:
        data = _get(TABLE_COMPANY_URLS)
        rows = data.get("Data", {}).get("Rows", []) or data.get("Data", []) or []
        result = []
        for r in rows:
            if r.get("active") in (True, 1, "true", "1"):
                result.append({
                    "company_name": r.get("company_name", "Unknown"),
                    "url": r.get("url", ""),
                    "record_id": r.get("id"),
                    "ezsite_record_id": r.get("id"),
                })
        return result
    except Exception as e:
        logger.error(f"EZSite get_active_company_urls error: {e}")
        return []

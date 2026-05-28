"""
AITable API client.
Handles all reads and writes to the 6 datasheets.
"""

import os
import hashlib
import requests
from datetime import date
from tenacity import retry, stop_after_attempt, wait_exponential

AITABLE_BASE = "https://api.aitable.ai/fusion/v1"


def _headers():
    return {
        "Authorization": f"Bearer {os.environ['AITABLE_API_TOKEN']}",
        "Content-Type": "application/json",
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _get(dst_id, params=None):
    url = f"{AITABLE_BASE}/datasheets/{dst_id}/records"
    r = requests.get(url, headers=_headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _post(dst_id, payload):
    url = f"{AITABLE_BASE}/datasheets/{dst_id}/records"
    r = requests.post(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _patch(dst_id, payload):
    url = f"{AITABLE_BASE}/datasheets/{dst_id}/records"
    r = requests.patch(url, headers=_headers(), json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


# ── Reads ──────────────────────────────────────────────────────────────────────

def get_active_job_titles():
    """Return list of job title strings where active = true."""
    dst = os.environ["DST_JOB_TITLES"]
    titles = []
    page = 1
    while True:
        data = _get(dst, params={"pageNum": page, "pageSize": 100})
        records = data.get("data", {}).get("records", [])
        if not records:
            break
        for r in records:
            fields = r.get("fields", {})
            if fields.get("active") and fields.get("title"):
                titles.append(fields["title"].strip())
        if len(records) < 100:
            break
        page += 1
    return titles


def get_active_company_urls():
    """Return list of {company_name, url} dicts where active = true."""
    dst = os.environ["DST_COMPANY_URLS"]
    urls = []
    data = _get(dst, params={"pageSize": 100})
    for r in data.get("data", {}).get("records", []):
        fields = r.get("fields", {})
        if fields.get("active") and fields.get("url"):
            urls.append({
                "company_name": fields.get("company_name", "Unknown"),
                "url": fields["url"],
                "record_id": r["recordId"],
            })
    return urls


def get_active_resume():
    """Return the extracted_text of the resume with is_active = true."""
    dst = os.environ["DST_RESUME"]
    data = _get(dst, params={"pageSize": 10})
    for r in data.get("data", {}).get("records", []):
        fields = r.get("fields", {})
        if fields.get("is_active"):
            return fields.get("extracted_text", "")
    return ""


def get_seen_job_hashes():
    """Return a set of all job_hash strings already processed."""
    dst = os.environ["DST_SEEN_JOBS"]
    hashes = set()
    page = 1
    while True:
        data = _get(dst, params={"pageNum": page, "pageSize": 1000})
        records = data.get("data", {}).get("records", [])
        if not records:
            break
        for r in records:
            h = r.get("fields", {}).get("job_hash")
            if h:
                hashes.add(h)
        if len(records) < 1000:
            break
        page += 1
    return hashes


# ── Writes ─────────────────────────────────────────────────────────────────────

def mark_job_seen(job_url: str):
    """Write a hash of the job URL to seen_jobs to prevent reprocessing."""
    dst = os.environ["DST_SEEN_JOBS"]
    job_hash = hashlib.md5(job_url.encode()).hexdigest()
    _post(dst, {"records": [{"fields": {
        "job_hash": job_hash,
        "date_seen": str(date.today()),
        "job_url": job_url,
    }}]})
    return job_hash


def save_job_posting(job: dict):
    """
    Save a new job to job_postings.
    job keys: title, company, location, job_board, job_url, description, date_found
    Returns the new record ID.
    """
    dst = os.environ["DST_JOB_POSTINGS"]
    resp = _post(dst, {"records": [{"fields": {
        "job_title": job["title"],
        "company": job["company"],
        "location": job.get("location", "India"),
        "job_board": job["job_board"],
        "job_url": job["job_url"],
        "description": job.get("description", ""),
        "date_found": str(date.today()),
        "status": "new",
        "match_score": job.get("match_score", 0),
    }}]})
    records = resp.get("data", {}).get("records", [])
    return records[0]["recordId"] if records else None


def save_application(app: dict):
    """
    Save AI-generated application data to applications table.
    app keys: job_url, company, job_title, match_score, cover_letter
    Returns the new record ID.
    """
    dst = os.environ["DST_APPLICATIONS"]
    resp = _post(dst, {"records": [{"fields": {
        "job_ref": app["job_url"],
        "company": app["company"],
        "job_title": app["job_title"],
        "match_score": app["match_score"],
        "cover_letter": app["cover_letter"],
        "job_url": app["job_url"],
        "status": "pending",
    }}]})
    records = resp.get("data", {}).get("records", [])
    return records[0]["recordId"] if records else None


def upload_attachment(dst_id: str, record_id: str, field_name: str, file_path: str):
    """Upload a local file as an attachment to a specific record field."""
    upload_url = f"{AITABLE_BASE}/datasheets/{dst_id}/attachments"
    with open(file_path, "rb") as f:
        fname = os.path.basename(file_path)
        # Step 1: upload file, get token
        r = requests.post(
            upload_url,
            headers={"Authorization": f"Bearer {os.environ['AITABLE_API_TOKEN']}"},
            files={"file": (fname, f)},
            timeout=60,
        )
        r.raise_for_status()
        token_data = r.json().get("data", {})
        token = token_data.get("token")
        if not token:
            raise RuntimeError(f"No attachment token returned: {r.text}")

    # Step 2: attach token to the record
    _patch(dst_id, {"records": [{"recordId": record_id, "fields": {
        field_name: [{"token": token}]
    }}]})


def update_company_url_last_scraped(record_id: str):
    dst = os.environ["DST_COMPANY_URLS"]
    _patch(dst, {"records": [{"recordId": record_id, "fields": {
        "last_scraped": str(date.today()),
    }}]})


def update_resume_extracted_text(record_id: str, text: str):
    dst = os.environ["DST_RESUME"]
    _patch(dst, {"records": [{"recordId": record_id, "fields": {
        "extracted_text": text,
    }}]})


def get_resume_record():
    """Return the full record (id + fields) for the active resume."""
    dst = os.environ["DST_RESUME"]
    data = _get(dst, params={"pageSize": 10})
    for r in data.get("data", {}).get("records", []):
        if r.get("fields", {}).get("is_active"):
            return r
    return None

"""
dashboard_generator.py
Reads job data from AITable and generates a static HTML dashboard.
Called at the end of every main.py run.
Output: docs/index.html (GitHub Pages serves from /docs folder)
"""

import os
import json
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

AITABLE_BASE = "https://api.aitable.ai/fusion/v1"


def _headers():
    return {"Authorization": f"Bearer {os.environ['AITABLE_API_TOKEN']}"}


def _fetch_all(dst_id: str) -> list:
    """Fetch all records from an AITable datasheet."""
    records = []
    page = 1
    while True:
        try:
            r = requests.get(
                f"{AITABLE_BASE}/datasheets/{dst_id}/records",
                headers=_headers(),
                params={"pageNum": page, "pageSize": 100},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            batch = data.get("data", {}).get("records", [])
            if not batch:
                break
            records.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        except Exception as e:
            logger.error(f"AITable fetch error: {e}")
            break
    return records


def _score_badge(score):
    try:
        s = int(score or 0)
    except:
        s = 0
    if s >= 70:
        return f'<span class="badge green">{s}</span>'
    elif s >= 50:
        return f'<span class="badge yellow">{s}</span>'
    else:
        return f'<span class="badge red">{s}</span>'


def _safe(val, default="—"):
    if val is None or val == "":
        return default
    return str(val)


def generate_dashboard():
    """Main function — fetch data from AITable and write HTML file."""
    logger.info("Generating HTML dashboard...")

    dst_jobs = os.environ.get("DST_JOB_POSTINGS", "")
    dst_apps = os.environ.get("DST_APPLICATIONS", "")

    # Fetch data
    all_job_records = _fetch_all(dst_jobs) if dst_jobs else []
    all_app_records = _fetch_all(dst_apps) if dst_apps else []

    # Separate new vs applied
    new_jobs = []
    applied_jobs = []
    for r in all_job_records:
        f = r.get("fields", {})
        status = str(f.get("status", "new")).lower()
        if status == "applied":
            applied_jobs.append(f)
        else:
            new_jobs.append(f)

    applications = [r.get("fields", {}) for r in all_app_records]

    # Sort newest first
    def sort_key(f):
        return str(f.get("date_found", "") or "")
    new_jobs.sort(key=sort_key, reverse=True)
    applied_jobs.sort(key=sort_key, reverse=True)
    applications.sort(key=lambda f: str(f.get("applied_date", "") or ""), reverse=True)

    last_updated = datetime.now().strftime("%d %b %Y, %I:%M %p IST")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Job Tracker — Rohan Wagh</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Inter', sans-serif; background: #f8f9fa; color: #1a1a1a; }}
  
  /* Nav */
  nav {{ background: #fff; border-bottom: 1px solid #e5e7eb; padding: 0 32px; display: flex; align-items: center; justify-content: space-between; height: 56px; position: sticky; top: 0; z-index: 100; }}
  nav .brand {{ font-weight: 700; font-size: 16px; color: #111; }}
  nav .tabs {{ display: flex; gap: 4px; }}
  nav .tab {{ padding: 6px 16px; border-radius: 6px; cursor: pointer; font-size: 14px; color: #555; border: none; background: none; transition: all 0.15s; }}
  nav .tab:hover {{ background: #f3f4f6; color: #111; }}
  nav .tab.active {{ background: #111; color: #fff; }}
  nav .updated {{ font-size: 12px; color: #999; }}

  /* Layout */
  .container {{ max-width: 1200px; margin: 0 auto; padding: 24px 24px; }}
  .page {{ display: none; }}
  .page.active {{ display: block; }}

  /* Stats bar */
  .stats {{ display: flex; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
  .stat {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 16px 20px; min-width: 140px; }}
  .stat .num {{ font-size: 28px; font-weight: 700; color: #111; }}
  .stat .label {{ font-size: 12px; color: #888; margin-top: 2px; }}

  /* Search + filter bar */
  .toolbar {{ display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }}
  .toolbar input, .toolbar select {{ padding: 8px 12px; border: 1px solid #e5e7eb; border-radius: 8px; font-size: 14px; outline: none; background: #fff; }}
  .toolbar input {{ flex: 1; min-width: 200px; }}
  .toolbar input:focus, .toolbar select:focus {{ border-color: #111; }}
  .count-label {{ font-size: 13px; color: #888; padding: 8px 0; white-space: nowrap; }}

  /* Table */
  .table-wrap {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  thead {{ background: #f9fafb; }}
  th {{ padding: 10px 14px; text-align: left; font-weight: 600; color: #555; font-size: 12px; text-transform: uppercase; letter-spacing: 0.4px; border-bottom: 1px solid #e5e7eb; white-space: nowrap; }}
  td {{ padding: 11px 14px; border-bottom: 1px solid #f3f4f6; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #fafafa; }}
  tr:nth-child(even) td {{ background: #fdfdfd; }}
  tr:nth-child(even):hover td {{ background: #fafafa; }}

  /* Badges */
  .badge {{ display: inline-block; padding: 3px 8px; border-radius: 20px; font-size: 12px; font-weight: 600; }}
  .badge.green {{ background: #dcfce7; color: #166534; }}
  .badge.yellow {{ background: #fef9c3; color: #854d0e; }}
  .badge.red {{ background: #fee2e2; color: #991b1b; }}
  .badge.grey {{ background: #f3f4f6; color: #555; }}
  .badge.blue {{ background: #dbeafe; color: #1e40af; }}

  /* Buttons */
  .btn {{ display: inline-block; padding: 5px 12px; border-radius: 6px; font-size: 12px; font-weight: 500; text-decoration: none; cursor: pointer; border: none; }}
  .btn-primary {{ background: #111; color: #fff; }}
  .btn-primary:hover {{ background: #333; }}
  .btn-outline {{ background: #fff; color: #555; border: 1px solid #d1d5db; }}
  .btn-outline:hover {{ background: #f9fafb; }}

  /* Job title */
  .job-title {{ font-weight: 600; color: #111; font-size: 13px; }}
  .job-title a {{ color: #111; text-decoration: none; }}
  .job-title a:hover {{ color: #4f46e5; text-decoration: underline; }}
  .company {{ color: #555; font-size: 12px; }}

  /* Cover letter modal */
  .modal-overlay {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.4); z-index: 1000; align-items: center; justify-content: center; }}
  .modal-overlay.open {{ display: flex; }}
  .modal {{ background: #fff; border-radius: 14px; padding: 28px; max-width: 600px; width: 90%; max-height: 80vh; overflow-y: auto; position: relative; }}
  .modal h3 {{ font-size: 16px; font-weight: 700; margin-bottom: 12px; color: #111; }}
  .modal p {{ font-size: 14px; line-height: 1.7; color: #444; white-space: pre-wrap; }}
  .modal-close {{ position: absolute; top: 16px; right: 20px; background: none; border: none; font-size: 20px; cursor: pointer; color: #888; }}

  /* Empty state */
  .empty {{ text-align: center; padding: 60px 20px; color: #aaa; }}
  .empty .icon {{ font-size: 40px; margin-bottom: 12px; }}
  .empty p {{ font-size: 14px; }}

  /* Page header */
  .page-header {{ margin-bottom: 20px; }}
  .page-header h1 {{ font-size: 22px; font-weight: 700; color: #111; }}
  .page-header p {{ font-size: 14px; color: #888; margin-top: 4px; }}

  /* Cover letter preview */
  .cl-preview {{ max-width: 240px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #888; font-size: 12px; }}
</style>
</head>
<body>

<nav>
  <div class="brand">🎯 Job Tracker</div>
  <div class="tabs">
    <button class="tab active" onclick="showPage('new-jobs')">New Jobs <span style="background:#ef4444;color:#fff;border-radius:10px;padding:1px 7px;font-size:11px;margin-left:4px;">{len(new_jobs)}</span></button>
    <button class="tab" onclick="showPage('applied-jobs')">Applied Jobs <span style="background:#6b7280;color:#fff;border-radius:10px;padding:1px 7px;font-size:11px;margin-left:4px;">{len(applications)}</span></button>
  </div>
  <div class="updated">Last updated: {last_updated}</div>
</nav>

<div class="container">

  <!-- NEW JOBS PAGE -->
  <div id="new-jobs" class="page active">
    <div class="page-header">
      <h1>New Jobs</h1>
      <p>Jobs found in the latest scrape — review and apply</p>
    </div>

    <div class="stats">
      <div class="stat"><div class="num">{len(new_jobs)}</div><div class="label">New Jobs</div></div>
      <div class="stat"><div class="num">{sum(1 for j in new_jobs if int(j.get('match_score') or 0) >= 70)}</div><div class="label">Strong Match (≥70)</div></div>
      <div class="stat"><div class="num">{sum(1 for j in new_jobs if int(j.get('match_score') or 0) >= 50 and int(j.get('match_score') or 0) < 70)}</div><div class="label">Good Match (50-69)</div></div>
      <div class="stat"><div class="num">{len(set(j.get('job_board','') for j in new_jobs))}</div><div class="label">Job Boards</div></div>
    </div>

    <div class="toolbar">
      <input type="text" id="jobs-search" placeholder="Search by title or company..." oninput="filterJobs()">
      <select id="jobs-board-filter" onchange="filterJobs()">
        <option value="">All Job Boards</option>
        {_board_options(new_jobs)}
      </select>
      <select id="jobs-score-filter" onchange="filterJobs()">
        <option value="">All Scores</option>
        <option value="70">Strong Match (≥70)</option>
        <option value="50">Good Match (≥50)</option>
      </select>
      <span class="count-label" id="jobs-count">{len(new_jobs)} jobs</span>
    </div>

    <div class="table-wrap">
      <table id="jobs-table">
        <thead>
          <tr>
            <th>Job Title / Company</th>
            <th>Location</th>
            <th>Board</th>
            <th>Date Found</th>
            <th>Match</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {_new_jobs_rows(new_jobs)}
        </tbody>
      </table>
      {_empty_state(new_jobs, "No new jobs found", "Run the scraper or check back later")}
    </div>
  </div>

  <!-- APPLIED JOBS PAGE -->
  <div id="applied-jobs" class="page">
    <div class="page-header">
      <h1>Applications</h1>
      <p>AI-processed jobs with tailored resumes and cover letters</p>
    </div>

    <div class="stats">
      <div class="stat"><div class="num">{len(applications)}</div><div class="label">Total Applications</div></div>
      <div class="stat"><div class="num">{sum(1 for a in applications if int(a.get('match_score') or 0) >= 70)}</div><div class="label">Strong Match</div></div>
      <div class="stat"><div class="num">{sum(1 for a in applications if str(a.get('status','')).lower() == 'applied')}</div><div class="label">Applied</div></div>
      <div class="stat"><div class="num">{sum(1 for a in applications if str(a.get('status','')).lower() == 'interview')}</div><div class="label">Interviews</div></div>
    </div>

    <div class="toolbar">
      <input type="text" id="apps-search" placeholder="Search by title or company..." oninput="filterApps()">
      <span class="count-label" id="apps-count">{len(applications)} applications</span>
    </div>

    <div class="table-wrap">
      <table id="apps-table">
        <thead>
          <tr>
            <th>Job Title / Company</th>
            <th>Date</th>
            <th>Match</th>
            <th>Cover Letter</th>
            <th>Status</th>
            <th>Apply</th>
          </tr>
        </thead>
        <tbody>
          {_applications_rows(applications)}
        </tbody>
      </table>
      {_empty_state(applications, "No applications yet", "Applications appear here after the AI processes new jobs")}
    </div>
  </div>

</div>

<!-- Cover Letter Modal -->
<div class="modal-overlay" id="cl-modal" onclick="closeModal(event)">
  <div class="modal">
    <button class="modal-close" onclick="document.getElementById('cl-modal').classList.remove('open')">✕</button>
    <h3 id="cl-modal-title">Cover Letter</h3>
    <p id="cl-modal-body"></p>
  </div>
</div>

<script>
function showPage(id) {{
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  event.target.classList.add('active');
}}

function filterJobs() {{
  const search = document.getElementById('jobs-search').value.toLowerCase();
  const board = document.getElementById('jobs-board-filter').value.toLowerCase();
  const score = parseInt(document.getElementById('jobs-score-filter').value || '0');
  const rows = document.querySelectorAll('#jobs-table tbody tr');
  let visible = 0;
  rows.forEach(row => {{
    const text = row.textContent.toLowerCase();
    const rowBoard = row.dataset.board || '';
    const rowScore = parseInt(row.dataset.score || '0');
    const matchSearch = !search || text.includes(search);
    const matchBoard = !board || rowBoard.toLowerCase().includes(board);
    const matchScore = !score || rowScore >= score;
    const show = matchSearch && matchBoard && matchScore;
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  }});
  document.getElementById('jobs-count').textContent = visible + ' jobs';
}}

function filterApps() {{
  const search = document.getElementById('apps-search').value.toLowerCase();
  const rows = document.querySelectorAll('#apps-table tbody tr');
  let visible = 0;
  rows.forEach(row => {{
    const text = row.textContent.toLowerCase();
    const show = !search || text.includes(search);
    row.style.display = show ? '' : 'none';
    if (show) visible++;
  }});
  document.getElementById('apps-count').textContent = visible + ' applications';
}}

function showCoverLetter(title, company, text) {{
  document.getElementById('cl-modal-title').textContent = title + ' — ' + company;
  document.getElementById('cl-modal-body').textContent = text || 'No cover letter available.';
  document.getElementById('cl-modal').classList.add('open');
}}

function closeModal(e) {{
  if (e.target.id === 'cl-modal') {{
    document.getElementById('cl-modal').classList.remove('open');
  }}
}}
</script>

</body>
</html>"""

    # Write to docs/index.html (GitHub Pages serves from /docs)
    os.makedirs("docs", exist_ok=True)
    output_path = "docs/index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    logger.info(f"Dashboard generated: {output_path} ({len(html)} chars)")
    return output_path


def _board_options(jobs):
    boards = sorted(set(j.get("job_board", "") for j in jobs if j.get("job_board")))
    return "".join(f'<option value="{b}">{b}</option>' for b in boards)


def _new_jobs_rows(jobs):
    if not jobs:
        return ""
    rows = []
    for j in jobs:
        title = _safe(j.get("job_title"))
        company = _safe(j.get("company"))
        location = _safe(j.get("location"))
        board = _safe(j.get("job_board"))
        date = _safe(j.get("date_found"))
        score = j.get("match_score", 0)
        url = _safe(j.get("job_url"), "")

        title_cell = f'<div class="job-title"><a href="{url}" target="_blank" rel="noopener">{title}</a></div><div class="company">{company}</div>' if url and url != "—" else f'<div class="job-title">{title}</div><div class="company">{company}</div>'
        apply_btn = f'<a href="{url}" target="_blank" rel="noopener" class="btn btn-primary">Apply →</a>' if url and url != "—" else '<span style="color:#ccc;font-size:12px">No link</span>'

        rows.append(f'''<tr data-board="{board}" data-score="{score or 0}">
          <td>{title_cell}</td>
          <td style="color:#555;font-size:12px">{location}</td>
          <td><span class="badge grey">{board}</span></td>
          <td style="color:#555;font-size:12px;white-space:nowrap">{date}</td>
          <td>{_score_badge(score)}</td>
          <td>{apply_btn}</td>
        </tr>''')
    return "\n".join(rows)


def _applications_rows(apps):
    if not apps:
        return ""
    rows = []
    for a in apps:
        title = _safe(a.get("job_title"))
        company = _safe(a.get("company"))
        date = _safe(a.get("applied_date"))
        score = a.get("match_score", 0)
        cover = _safe(a.get("cover_letter"), "")
        status = _safe(a.get("status"), "pending").lower()
        url = _safe(a.get("job_url"), "")

        # Status badge
        status_colors = {"pending": "grey", "applied": "green", "interview": "blue", "rejected": "red"}
        status_badge = f'<span class="badge {status_colors.get(status, "grey")}">{status.title()}</span>'

        # Cover letter button
        if cover and cover != "—":
            escaped = cover.replace("'", "\\'").replace("\n", "\\n")[:2000]
            cl_btn = f'<button class="btn btn-outline" onclick="showCoverLetter(\'{title}\', \'{company}\', \'{escaped}\')">View</button>'
        else:
            cl_btn = '<span style="color:#ccc;font-size:12px">—</span>'

        apply_btn = f'<a href="{url}" target="_blank" class="btn btn-primary">Apply →</a>' if url and url != "—" else '<span style="color:#ccc;font-size:12px">—</span>'

        title_cell = f'<div class="job-title">{title}</div><div class="company">{company}</div>'

        rows.append(f'''<tr>
          <td>{title_cell}</td>
          <td style="color:#555;font-size:12px;white-space:nowrap">{date}</td>
          <td>{_score_badge(score)}</td>
          <td>{cl_btn}</td>
          <td>{status_badge}</td>
          <td>{apply_btn}</td>
        </tr>''')
    return "\n".join(rows)


def _empty_state(items, title, subtitle):
    if items:
        return ""
    return f'<div class="empty"><div class="icon">📭</div><p><strong>{title}</strong><br>{subtitle}</p></div>'

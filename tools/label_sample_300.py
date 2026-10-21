"""Create a 300-job labeled dataset for v2 tests and save it in DeepEval Golden format.

Sample:
  60  jobs  from data/labelled_sample.jsonl  (existing hand labels kept as-is)
  240 jobs  sampled from jobs_raw.jsonl      (rule-based labels applied here)

Matching rules mirror OUTPUT_FORMAT.json:
  • live:     http_status 404/410 → NO
  • company:  scraped.company matches profile after normalization → else NO
  • title:    every word of a profile title appears in scraped.title → else NO
  • location: scraped.location contains a covered town → else NO
  • all pass  → YES

Output:
  data/labelled_300.jsonl          one JSON line per job (same schema as labelled_sample.jsonl
                                   plus the raw job fields for page/scraped)
  data/labelled_300_deepeval.json  DeepEval EvaluationDataset (Golden objects)
"""

from __future__ import annotations

import json
import random
import re
import shutil
import sys
from pathlib import Path

from deepeval.dataset import EvaluationDataset
from deepeval.dataset.golden import Golden

REPO = Path(__file__).parent.parent
DATA = REPO / "data"
PROFILE_DIR = DATA / "user_search_inputs" / "profile_a"

SAMPLE_SIZE = 300
SEED = 42


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------


def load_profile() -> dict:
    with (PROFILE_DIR / "company_searches.json").open() as f:
        companies = json.load(f)["companies"]
    with (PROFILE_DIR / "job_title_searches.json").open() as f:
        titles = json.load(f)["titles"]
    with (PROFILE_DIR / "location_searches.json").open() as f:
        locations = json.load(f)["locations"]
    return {"companies": companies, "titles": titles, "locations": locations}


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

_LEGAL_SUFFIXES = {
    "ltd",
    "limited",
    "plc",
    "group",
    "holdings",
    "international",
    "uk",
    "services",
    "engineering",
    "technologies",
    "technology",
    "systems",
    "solutions",
    "company",
    "co",
    "inc",
    "gmbh",
    "corp",
    "corporation",
    "the",
}


def _normalize_company(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^\w\s]", " ", name)  # punctuation → space
    parts = [p for p in name.split() if p]
    # strip leading "the"
    while parts and parts[0] == "the":
        parts = parts[1:]
    # strip trailing legal words
    while parts and parts[-1] in _LEGAL_SUFFIXES:
        parts = parts[:-1]
    return " ".join(parts)


def _normalize_word(word: str) -> str:
    w = re.sub(r"[^\w]", "", word.lower())
    if len(w) > 2 and w.endswith("s"):
        w = w[:-1]
    return w


# ---------------------------------------------------------------------------
# Matching logic
# ---------------------------------------------------------------------------


def _find_matching_company(scraped_company: str, profile_companies: list[dict]) -> str | None:
    norm = _normalize_company(scraped_company)
    for c in profile_companies:
        if _normalize_company(c["name"]) == norm:
            return c["name"]
    return None


def _find_matching_titles(scraped_title: str, profile_titles: list[str]) -> list[str]:
    job_words = {_normalize_word(w) for w in scraped_title.split()}
    matched = []
    for pt in profile_titles:
        if all(_normalize_word(w) in job_words for w in pt.split()):
            matched.append(pt)
    return matched


def _all_location_towns(loc: dict) -> list[str]:
    return [loc["name"].lower()] + [inc.lower() for inc in loc.get("includes", [])]


def _find_matching_locations(scraped_location: str, profile_locations: list[dict]) -> list[str]:
    if not scraped_location:
        return []
    loc_lower = scraped_location.lower()
    matched = []
    for loc in profile_locations:
        if loc["type"] == "remote":
            if any(kw in loc_lower for kw in ["remote", "home-based", "work from home", "home based"]):
                matched.append(loc["name"])
        else:
            if any(town in loc_lower for town in _all_location_towns(loc)):
                matched.append(loc["name"])
    return list(dict.fromkeys(matched))  # dedup, preserve order


def label_job(job: dict, profile: dict) -> dict:
    """Return a label dict with keys: decision, reason, matched_company,
    matched_job_title, matched_location."""
    page = job.get("page") or {}
    scraped = job.get("scraped") or {}
    http_status = page.get("http_status")

    # 1. Live check
    if http_status in (404, 410):
        return {
            "decision": "no",
            "reason": "no: the employer's page says the job is gone (404/410)",
            "matched_company": None,
            "matched_job_title": [],
            "matched_location": [],
        }

    # 2. Blocked / unreadable (403 or null without structured content)
    if http_status == 403:
        return {
            "decision": "no",
            "reason": "no: the page could not be read (blocked or not rendered), so the job is not confirmed open",
            "matched_company": None,
            "matched_job_title": [],
            "matched_location": [],
        }

    # 3. Company
    scraped_company = scraped.get("company") or ""
    matched_company = _find_matching_company(scraped_company, profile["companies"])
    if matched_company is None:
        return {
            "decision": "no",
            "reason": "no: the company is not on the profile's company list",
            "matched_company": None,
            "matched_job_title": [],
            "matched_location": [],
        }

    # 4. Title
    scraped_title = scraped.get("title") or ""
    matched_titles = _find_matching_titles(scraped_title, profile["titles"])
    if not matched_titles:
        return {
            "decision": "no",
            "reason": f"no: the real title ({scraped_title}) fits none of the profile's titles",
            "matched_company": None,
            "matched_job_title": [],
            "matched_location": [],
        }

    # 5. Location
    scraped_location = scraped.get("location") or ""
    matched_locs = _find_matching_locations(scraped_location, profile["locations"])
    if not matched_locs:
        return {
            "decision": "no",
            "reason": f"no: the job's location ({scraped_location}) is in none of the profile's locations",
            "matched_company": None,
            "matched_job_title": [],
            "matched_location": [],
        }

    return {
        "decision": "yes",
        "reason": "yes: open job at a listed company, real title and a town the employer names fit",
        "matched_company": matched_company,
        "matched_job_title": matched_titles,
        "matched_location": matched_locs,
    }


# ---------------------------------------------------------------------------
# Golden builder
# ---------------------------------------------------------------------------


def _job_input_str(job: dict) -> str:
    page = job.get("page") or {}
    return json.dumps(
        {
            "job_id": job["job_id"],
            "scraped": job.get("scraped"),
            "source_url": job.get("source_url"),
            "page": {
                "http_status": page.get("http_status"),
                "title_tag": page.get("title_tag"),
                "h1": page.get("h1"),
                "structured_job": page.get("structured_job"),
            },
        },
        ensure_ascii=False,
    )


def _profile_context(profile: dict) -> str:
    return json.dumps(
        {
            "profile_id": "a",
            "companies": [c["name"] for c in profile["companies"]],
            "titles": profile["titles"],
            "locations": [
                {"name": loc["name"], "type": loc["type"], "includes": loc.get("includes", [])}
                for loc in profile["locations"]
            ],
        },
        ensure_ascii=False,
    )


def make_golden(job: dict, label: dict, profile_ctx: str) -> Golden:
    return Golden(
        input=_job_input_str(job),
        expected_output=json.dumps(
            {
                "decision": label["decision"],
                "matched_company": label["matched_company"],
                "matched_job_title": label["matched_job_title"],
                "matched_location": label["matched_location"],
            },
            ensure_ascii=False,
        ),
        retrieval_context=[profile_ctx],
        additional_metadata={
            "job_id": job["job_id"],
            "decision": label["decision"],
            "reason": label["reason"],
            "matched_company": label["matched_company"],
            "matched_job_title": label["matched_job_title"],
            "matched_location": label["matched_location"],
        },
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    random.seed(SEED)

    profile = load_profile()
    profile_ctx = _profile_context(profile)

    # Load existing labels
    labelled_path = DATA / "labelled_sample.jsonl"
    existing_labels: dict[str, dict] = {}
    with labelled_path.open() as f:
        for line in f:
            row = json.loads(line)
            existing_labels[row["job_id"]] = row

    # Load all jobs indexed by job_id
    jobs_raw_path = DATA / "jobs_raw.jsonl"
    all_jobs: dict[str, dict] = {}
    with jobs_raw_path.open() as f:
        for line in f:
            job = json.loads(line)
            all_jobs[job["job_id"]] = job

    # 60 from labelled_sample (preserve existing labels exactly)
    labelled_ids = list(existing_labels.keys())
    assert len(labelled_ids) == 60, f"Expected 60 in labelled_sample, got {len(labelled_ids)}"

    # 240 from the rest
    remaining_ids = [jid for jid in all_jobs if jid not in existing_labels]
    extra_ids = random.sample(remaining_ids, min(SAMPLE_SIZE - len(labelled_ids), len(remaining_ids)))

    goldens: list[Golden] = []
    rows: list[dict] = []

    for jid in labelled_ids:
        job = all_jobs.get(jid)
        if job is None:
            print(f"WARNING: labelled job {jid} not in jobs_raw — skipping", file=sys.stderr)
            continue
        label = existing_labels[jid]
        goldens.append(make_golden(job, label, profile_ctx))
        rows.append({"job_id": jid, **label})

    for jid in extra_ids:
        job = all_jobs[jid]
        label = label_job(job, profile)
        goldens.append(make_golden(job, label, profile_ctx))
        rows.append({"job_id": jid, **label})

    # Collect raw jobs in sample order (for the feed file)
    sampled_jobs = []
    for jid in labelled_ids:
        job = all_jobs.get(jid)
        if job is not None:
            sampled_jobs.append(job)
    for jid in extra_ids:
        sampled_jobs.append(all_jobs[jid])

    # ---- golden_300/ — pipeline-ready input feed + profile (mirrors data/golden/) ----
    golden_dir = DATA / "golden_300"
    golden_dir.mkdir(exist_ok=True)
    out_feed = golden_dir / "jobs.jsonl"
    with out_feed.open("w", encoding="utf-8") as f:
        for job in sampled_jobs:
            f.write(json.dumps(job, ensure_ascii=False) + "\n")
    # Copy profile_a into golden_300/user_search_inputs/profile_a/
    golden_profile_dst = golden_dir / "user_search_inputs" / "profile_a"
    if golden_profile_dst.exists():
        shutil.rmtree(golden_profile_dst)
    shutil.copytree(PROFILE_DIR, golden_profile_dst)

    # ---- Save JSONL (same schema as labelled_sample.jsonl) ----
    out_jsonl = DATA / "labelled_300.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ---- Save DeepEval EvaluationDataset ----
    EvaluationDataset(goldens=goldens)
    out_json = DATA / "labelled_300_deepeval.json"
    goldens_serialised = [g.model_dump() for g in goldens]
    with out_json.open("w", encoding="utf-8") as f:
        json.dump({"goldens": goldens_serialised}, f, ensure_ascii=False, indent=2, default=str)

    # ---- Stats ----
    yes_count = sum(1 for r in rows if r["decision"] == "yes")
    no_count = len(rows) - yes_count
    print(f"Labeled {len(rows)} jobs total")
    print(f"  YES: {yes_count}  ({yes_count / len(rows) * 100:.1f}%)")
    print(f"  NO:  {no_count}  ({no_count / len(rows) * 100:.1f}%)")
    print(f"  from labelled_sample: {len(labelled_ids)}")
    print(f"  rule-labeled new:     {len(extra_ids)}")
    from collections import Counter

    reasons = Counter()
    for r in rows:
        if r["decision"] == "no":
            # Extract short reason tag
            reason = r["reason"]
            if "404" in reason or "410" in reason:
                reasons["dead link"] += 1
            elif "company is not" in reason:
                reasons["company mismatch"] += 1
            elif "title" in reason and "fits none" in reason:
                reasons["title mismatch"] += 1
            elif "location" in reason:
                reasons["location mismatch"] += 1
            elif "blocked" in reason:
                reasons["blocked/unreadable"] += 1
            else:
                reasons["other"] += 1
    print("\nNO breakdown:")
    for reason, count in reasons.most_common():
        print(f"  {reason}: {count}")
    print(f"\nSaved: {out_feed}  ({len(sampled_jobs)} raw jobs — pipeline input feed)")
    print(f"Saved: {golden_profile_dst.parent.parent}  (golden_300/ directory with profile_a)")
    print(f"Saved: {out_jsonl}  (labels, same schema as labelled_sample.jsonl)")
    print(f"Saved: {out_json}  (DeepEval EvaluationDataset)")


if __name__ == "__main__":
    main()

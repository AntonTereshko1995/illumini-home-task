# Notes

## LLM Provider

[Vercel AI Gateway](https://vercel.com/ai-gateway/models/jev) is a good fit here — the task is essentially data comparison, so the most important thing is normalizing the data correctly.

---

## Architecture

### How the runtime builds the recruiter profile

`load_search_inputs()` in [worker_runtime.py](v1/shared/patterns/worker_runtime.py) reads the `profile_a/` directory and **merges three files into one dict**:

```python
{
  "profile_id": "a",
  "companies":  [{"name": "Aire Calder", "industry": null}, ...],  # from company_searches.json
  "titles":     ["Controls Engineer", "Mechanical Engineer", ...],  # from job_title_searches.json
  "locations":  [{"name": "Warrington", "type": "sub_region", ...}, ...]  # from location_searches.json
}
```

This dict becomes `context["profile"]` and travels through the entire pipeline.

### Job structure in `jobs_raw.jsonl`

Each line looks like:

```json
{
  "job_id": "J123456",
  "scraped": {
    "title":    "Controls Engineer",
    "company":  "Aire Calder",
    "location": "Warrington",
    "salary":   "£45,000"
  },
  "source_url": "...",
  "page": {
    "http_status": 200,
    "title_tag":   "Controls Engineer | Aire Calder",
    "h1":          "Controls Engineer",
    "meta":        {},
    "visible_text": "...",
    "structured_job": {
      "title":     "Controls Engineer",
      "company":   "Aire Calder",
      "locations": ["Warrington"]
    }
  }
}
```

`scraped.*` — what the scraper extracted from markup (often truncated, empty, or wrong).
`page.*` — the raw page fetched once: HTTP status plus all visible fields.

### Pipeline flow

```
jobs_raw.jsonl
    │
    ▼ load_job_feed
    │  → reads line by line; row["page"] and row["scraped"] available
    │
    ▼ normalise_job_rows
    │  → picks only scraped.{title, company, location, salary}
    │  → page is kept as-is in row["page"]
    │
    ▼ drop_duplicate_jobs
    │  → dedup by key title|company
    │
    ▼ resolve_job_town
    │  → takes row["location"] from scraped, looks it up in TOWNS dict
    │  → adds: row["town"], row["region"], row["country"]
    │
    ▼ match_jobs   ← profile_a files meet jobs here
    │
    │  [company check]   row["company"] ∈ {c["name"] for c in profile["companies"]}?
    │  [title check]     any t in profile["titles"] is a substring of row["title"]?
    │  [location check]  row["town"] ∈ towns_covered(loc) for any loc in profile["locations"]?
    │
    ▼ portal_matches_output
       → writes runs/<trace_id>/profile_a_matched.jsonl
```

---

## Known Bugs in v1

### 1. No dead-link filter (critical)

The spec says HTTP 404 and 410 must always be rejected. v1 has no such module.

| Status    | Count | Note                           |
| --------- | ----- | ------------------------------ |
| HTTP 200  | 868   | live                           |
| HTTP 403  | 455   | blocked (live, scraper failed) |
| HTTP 404  | 46    | should be rejected             |
| HTTP 410  | 129   | should be rejected             |
| HTTP 405  | 3     | live (method not supported)    |
| HTTP None | 10    | no page at all                 |

8 of 49 "no" labels in `labelled_sample` are 404/410 jobs — they currently pass through to `match_jobs`.

---

### 2. `resolve_job_town` drops 10 of 11 correct answers

Checked all "yes" jobs from `labelled_sample` against the TOWNS dict:

| job_id  | scraped.location             | Passes?         |
| ------- | ---------------------------- | --------------- |
| J685745 | "Runcorn"                    | ✓ only one     |
| J849031 | "Birmingham, United Kingdom" | ✗              |
| J442509 | "Crewe"                      | ✗ not in TOWNS |
| J576140 | "2 Locations"                | ✗              |
| J858474 | "Knutsford, Radbroke Hall"   | ✗              |
| J355784 | "Bangor Bus Depot"           | ✗              |
| J936283 | "Birmingham, United Kingdom" | ✗              |

Root causes:

- **Country suffix**: `"Birmingham, United Kingdom"` — need to strip `, United Kingdom`
- **Unknown cities**: `"Crewe"`, `"Knutsford"` — present in profile `includes`, missing from TOWNS
- **Placeholders**: `"2 Locations"`, `"10 Locations"` — must fall back to `structured_job.locations`
- **Addresses**: `"Bangor Bus Depot"`, `"Knutsford, Radbroke Hall"` — need city extraction
- **Empty location**: 420 jobs have no location — all silently lost

---

### 3. `scraped.title` contains abbreviations and truncations

The scraper frequently stores garbage instead of the real title:

| scraped.title | structured_job / title_tag                   |
| ------------- | -------------------------------------------- |
| "HC engineer" | "HV Commissioning Engineer"                  |
| "MD engineer" | "Mechanical Design Engineer"                 |
| "SC systems"  | "Software & Control Systems Engineers"       |
| "SM manager"  | "Senior Marketing Manager - Financial Lines" |

`match_jobs` compares against `row["title"]` which comes from `scraped.title`. The real title is in `page.title_tag` or `page.structured_job.title` — matching must use those.

---

### 4. `matched_titles` — substring instead of word-by-word matching

```python
# v1: substring containment
return [t for t in titles if t in job_title]
```

Spec requires: *"every word of the profile title appears in the job's real title in any order, ignoring case, punctuation & a trailing plural s"*.

What breaks with substring:

- `"cnc miller" in "CNC Miller"` → `False` (case-sensitive)
- `"Quality Engineer" in "Quality and Warranty Engineer"` → `False` (words not adjacent)
- `"Controls Engineer" in "Senior Controls Engineer"` → `True` — works by coincidence

From labelled data: job `J602066` has title `"Quality and Warranty Engineer"` and should match profile title `"Quality Engineer"` (both words present), but substring check returns `False`.

---

### 5. Company matching — exact equality against `scraped.company` only

```python
# v1
if row["company"] not in companies:  # exact string from scraped.company
    reject(row, "COMPANY_NOT_LISTED")
```

Problems:

- `scraped.company` often contains a different company than what's on the page (e.g. `scraped="Viaduct Thornbury Systems"` vs `structured_job.company="Delta North Granary"`)
- Profile names include legal suffixes (`Ltd`, `ENGINEERING LTD`, `The Group`, `Holdings`, `UK`) that may differ from scraped data — spec requires fuzzy matching ignoring those suffixes

From labelled data: `J809819` — `scraped.company = "Cobalt Zephyr Holdings"`, profile contains `"Cobalt Zephyr"` → should match, but doesn't due to the `Holdings` suffix.

Spec also requires checking the company name **across the whole page** (title_tag, h1, URL, visible_text, structured_job) — pipeline only looks at `scraped.company`.

---

### 6. Remote location type not implemented

Profile contains:

```json
{"name": "Remote (UK)", "type": "remote", "includes": ["Remote", "Home-based", "Work from home"]}
```

`towns_covered()` returns `{"Remote (UK)", "Remote", "Home-based", "Work from home"}`, but `row["town"]` comes from the TOWNS dict which contains none of these values. Remote jobs never match.

Spec: remote = jobs where the employer explicitly states remote/home-based in that country — must check `visible_text` and `structured_job.locations`.

---

### 7. `structured_job.locations` is never used

135 jobs have `structured_job.locations` — a list of strings like `["Birmingham, GB"]`, `["manchester, Lancashire, United Kingdom"]`, `["United Kingdom", "Remote"]`. This is the most reliable location source, but the pipeline ignores it entirely.

---

### 8. `normalise_job_rows` — silent error swallowing

```python
try:
    scraped = raw["scraped"]
    rows.append({...})
except Exception:
    pass  # row silently lost — no rejection reason, no SLI entry
```

---

### 9. `parse_salary` crashes on real data

Values in the feed: `"£50K per Annum"`, `"1K - 3K per Annum"`, `"$2 per Annum"` — all cause `ValueError` inside `int(...)`. Not critical (only 12 jobs have salary), but combined with the `except Exception: pass` above, rows are silently lost.

---

### 10. Dedup by `title|company` instead of `job_id`

[drop_duplicate_jobs.py:18](v1/workers/job_matcher/modules/drop_duplicate_jobs.py#L18): key `f"{row['title']}|{row['company']}"`.

Two different jobs at the same company with the same title in different cities will be incorrectly merged. The correct key is `job_id`.





## Data Analysis — data/ (excluding golden)

### 1. jobs_raw.jsonl — 1,529 jobs

HTTP status breakdown:

| Status        | Count | %     |
|---------------|-------|-------|
| 200 OK        | 868   | 56.8% |
| 403 Forbidden | 455   | 29.8% |
| 410 Gone      | 129   | 8.4%  |
| 404 Not Found | 46    | 3.0%  |
| Other / empty | 31    | 2.0%  |

43% of jobs are inaccessible. Of those, 11.4% are dead links (404/410) that should be filtered.

Field fill rates:

| Field                 | Filled                    |
|-----------------------|---------------------------|
| scraped.title         | 100%                      |
| scraped.company       | 100%                      |
| scraped.location      | 72.5% (420 missing)       |
| scraped.salary        | 0.8% (12 of 1,529)        |
| page.title_tag        | 39.8%                     |
| page.meta             | 38.8%                     |
| page.structured_job   | 27.1%                     |
| page.h1               | 16.0%                     |
| page.visible_text     | 0% (empty in entire dataset) |

**Critical finding:** `visible_text` is completely empty across the whole dataset. The company-matching rule from OUTPUT_FORMAT.json (search across page body text) cannot be applied — there is no data to search.

### 2. Location signals

- Unique location strings: 340
- 212 jobs have `"2 Locations"`, 46 have `"3 Locations"`, etc. — these are not parsed
- Top real locations: London (37), Derby (32), Bristol (24), Glasgow (17)
- Matches against profile cities (naive search): 164 / 1,529 (10.7%)

### 3. Title signals (word-level matching)

- Unique job titles: 1,348
- Matches against profile (all words present in title): 118 / 1,529 (7.7%)
- Top matched profile titles: Controls Engineer (24), Electrical Engineer (12), Design Engineer (10), Operations Manager (9), Maintenance Technician (9)

### 4. Company signals

- Profile companies: 408 (199 with industry specified)
- Company matches (normalised): 1,049 / 1,529 (68.6%)
- High match rate because the entire feed appears to have been generated from the same company list.

### 5. Signal intersection

| Condition                          | Jobs         |
|------------------------------------|--------------|
| Company only                       | 1,049 (68.6%)|
| Title only                         | 118 (7.7%)   |
| Location only                      | 164 (10.7%)  |
| All three (company + title + location) | 35 (2.3%) |

### 6. labelled_sample.jsonl — 60 labelled jobs

- yes (match): 11 (18.3%)
- no: 49 (81.7%)

All 60 job_ids are present in jobs_raw.jsonl. Of the 11 positives, only 9 have `matched_company` / `matched_location` / `matched_job_title` filled; 2 have those fields empty despite `decision=yes` — an annotation anomaly.

---

## Data investigation: run `20261020T153054` vs `profile_a` inputs

### Pipeline funnel — where jobs are lost

```
load_job_feed        1529  →  pass: 1529 (100%)
drop_duplicates      1517  →  pass: 1445 (95.3%)  | rejected: 72 DUPLICATE
resolve_job_town     1445  →  pass:     6 (0.4%)  | rejected: 1439 UNKNOWN_LOCATION  ← BOTTLENECK
match_jobs              6  →  pass:     2 (33.3%) | rejected: 3 COMPANY_NOT_LISTED, 1 NO_TITLE_MATCH
OUTPUT                  2 jobs
```

### Signal correlation with the dataset

| Dimension                                        | Matches    | % of 1,529 |
|--------------------------------------------------|------------|------------|
| Company (exact match)                            | **1,021**  | 66.8%      |
| Location (token match against towns)             | **136**    | 8.9%       |
| Title (word-match against profile)               | ~**160**   | ~10.5%     |
| **Triple intersection (manual analysis)**        | **56**     | 3.7%       |
| Of which false-geo (Liverpool NSW, Warrington PA…) | −6       |            |
| **Real UK jobs that should match**               | **~48–50** |            |
| **Worker found**                                 | **2**      | 0.13%      |

### Root cause: `resolve_job_town` only handles bare-city lookup

Location format breakdown in the dataset:

| Format                          | Count       | Worker handling                          |
|---------------------------------|-------------|------------------------------------------|
| `"City, United Kingdom"`        | 567 (37%)   | ❌ UNKNOWN_LOCATION                      |
| Bare city (1–2 words)           | 459 (30%)   | ✅ only if in hardcoded dict             |
| Empty string                    | 420 (27.5%) | ❌ UNKNOWN_LOCATION                      |
| `"Hybrid - 2 days Warrington"`  | 1 (0.1%)    | ❌ UNKNOWN_LOCATION                      |
| US/AU false positives           | 15 (1%)     | needs country filter                     |

Of the 567 jobs with `"City, United Kingdom"` format — **80 have a city from the profile** (Manchester, Birmingham, Liverpool, etc.) and all are lost because the resolver cannot strip the `, United Kingdom` suffix.

### The 6 jobs that passed the resolver

Only jobs with a **bare city name** (`Wrexham`, `Chester`, `Runcorn`) hit the hardcoded TOWNS dict. Of those:

- **2 passed** (Inkwell Copperleaf Group — present in companies list, Wrexham → North Wales)
- **3 rejected** at COMPANY_NOT_LISTED (`Mersey Ironbridge`, `Moorside Millrace` — not in the list)
- **1 rejected** at NO_TITLE_MATCH (`Software Engineer III, Digital Pathology…` — `systems engineer` is too weak a match)

### Top missed patterns (54 missed of 56)

53 of 54 are blocked at `resolve_job_town`. Main patterns:

- `"Bolton, GB"` — 5 Controls Engineer jobs @ Aire Calder / Aire Northwind / Ancoats Castlefield
- `"Manchester, United Kingdom"` — 4 jobs
- `"Liverpool, United Kingdom"` — 4 jobs
- `"Birmingham, United Kingdom"` — 6 jobs
- `"Knutsford, Radbroke Hall"` — 3 jobs at Lowther Brindley
- `"Wolverhampton, United Kingdom"` — 2 jobs

### Conclusion

The worker **works** — architecture and contracts are correct. But `resolve_job_town` is an intentionally broken module (noted in CLAUDE.md): it uses exact-match against a tiny hardcoded dict, whereas the real requirement is parsing multi-format location strings. Fixing this module alone would raise output from 2 to ~48 jobs (~24×).

# Brief

## The Task
### Background
A recruiter user will provide their search inputs at `data\user_search_inputs`, which are:
- Companies they wish to search the career pages of e.g. Deloitte
- Job titles they wish to search for e.g. Senior Consultant
- Locations they wish to find these roles e.g. United Kingdom

### The Task
This task is matching 1,500 real mass-scraped jobs at `data\jobs_raw.jsonl` to these search inputs. This process is downstream of the career page scraping process, all data provided is local & you are **not** expected to perform any live searches.

We have provided a version 1 located at `v1\workers\job_matcher`, which provides a basic framework to start from, however it is deliberately broken & does not match jobs accurately. See the README for a deeper understanding.

Recruiters are paid a % fee, from 15-30% of a salary, meaning sending a £100K salary Candidate to an open role & then being hired, earning a Recruitment company £15-£30K. Recruitment is critically based off speed, Career Pages are typically the first place a job goes live before hitting job boards such as LinkedIn, Indeed, Reed etc, meaning if we can successfully scrape career pages & filter accurately, this can create strong leads for Recruiters.

### What we're looking for
This task is to create a successfully matching codebase that matches our production job_matcher answers to within 90%, on a dataset we hold privately.

More importantly, we're assessing how you get there:
- Clear, concise code: a small, well-scoped solution with clear trade-offs is better than a big one.
- Efficiency: think about time and space complexity, it must run 200k jobs in under 20 minutes.
- Well-written tests for the rules & logic you implement.
- Your process: commit little and often, it's important for us to see a timeline

We expect AI-assisted coding tools will be used, but make sure PLAN.md, DECISIONS.md & NOTES.md are concisely written documents.


## The Build
### Matching standards
- The matching is pass / fail. A job goes in only when all three match: the company, at least one job title, at least one location.
- Precision matters more than volume, the core selling point of this product is it doesn't produce noise.
- A job in several places is in if ANY of them matches: "Bristol, Manchester" for a recruiter with "Bristol" in their search inputs, this is a pass.
- The company must appear somewhere on the job page (declared company, heading, title tag, URL or body text). That's only a loose validator to ensure we have the correct career page, because the search upstream should have already picked the correct company's career page.
- A recruiter needs evidence the job is live. A dead link (404 / 410) never goes in.
- Full definitions: [OUTPUT_FORMAT.json](OUTPUT_FORMAT.json).


### Engineering preferences
- An LLM API will be provided before the task, see the example at .env.example. These are live API calls from API keys with capped budgets & there will likely be cases where an LLM is required, you should aim for £1 target, £3 max spend.
- The use of LLM matching should be at your discretion, although keep in mind the cost vs matching via code.
- It must run on 200k jobs in under 20 minutes.
- `tools/make_scale_feed.py` builds the 200,000-job test feed from `data/jobs_raw.jsonl`.
- No scraping happens, each job already carries the page we fetched once (`page.http_status` + what it showed). Blocked pages, dead links, blank locations, title mismatches, wrong company on the page. Japanese-script locations and "3 Locations" placeholders are all in that data. Each needs a defensible policy.

### The 4 phases
Plan     - 15-30 minutes - `PLAN.md`, handwritten documents 
Build    - 15-30 minutes - commits
Tune     - 15-30 minutes - commits
Complete - 15-30 minutes - `NOTES.md`

1-2 hours total (self-timed), there are no bonus points for exceeding the time limit. Log your start and end in `NOTES.md`, log every decision in `DECISIONS.md` as you make it.

Commit little and often, at every step, not once at the end, we want to see the development of commits over a timeline.


## Your inputs
All inputs live in `data\`.

### Search inputs
Each recruiter has a folder at `data\user_search_inputs\`, e.g. `profile_a`, holding the three searches they set up:
`company_searches.json` lists the companies they recruit for (the industry field is context only & about half filled)
`job_title_searches.json` lists the job titles they place
`location_searches.json` lists where they work, with every location carrying a name, a country, a type & an `includes` list of the towns it covers.

A `city` covers its own name & its includes, a `sub_region` (a region, nation or county) also covers any town inside it, and `remote` covers jobs the employer says are remote or home-based in that country, but a job in another country is never inside a location, whatever the town is called.

Every file carries the same `profile_id`, which goes on every output line, and the starter reads the folder back into one profile for you through `load_search_inputs` in `v1\shared\patterns\worker_runtime.py`. We grade on a different recruiter's folder, so nothing should be hard-coded to `profile_a`.

### The jobs
`data\jobs_raw.jsonl` holds about 1,500 jobs, one per line. Each has a `job_id` to copy to your output unchanged, the `scraped` fields our scraper stored (title, company, location & salary, which are often abbreviated, blank or wrong), the `source_url` it was found at (anonymised, so it will not load), and the `page` exactly as we fetched it once: its `http_status`, then whatever it showed, which is the title tag, the h1, the meta tags, the visible text and `structured_job`, the job facts the page declared itself (title, company & locations). Any of these can be missing or empty.

### Answers & tests
`data\labelled_sample.jsonl` has 60 jobs with the right decision, matched company, job titles & locations, and reason, and is the only answer key you get. `data\golden\` holds a tiny feed & profile the starter already passes, which `make test` runs.




---
name: jev-implementation-pattern
description: Real jev call pattern used in this project — compact state + flat Noul battery + Choice for rejection_reason
metadata: 
  node_type: memory
  type: project
  originSessionId: d843f2ef-4cf3-42f4-a402-c7d79ac702a5
---

The project already uses jev in `stage_agent` (seen in `runs/20261023T185439/llm_prompts.jsonl`).

**Pattern observed:**
- `state`: compact dict — `company`, `title`, `location_strings`, `is_remote`, `title_tag`, `url`. No page text.
- `company` question: single Noul with ALL target companies listed in instructions (not one Noul per company).
- `title_N` questions: one Noul per profile title search term (57 titles → 57 questions).
- `loc_N` questions: one Noul per profile location (12 locations → 12 questions).
- `rejection_reason`: Choice over `{WRONG_COMPANY, WRONG_TITLE, WRONG_LOCATION, WRONG_COUNTRY, DEAD_LINK, MULTI_FAIL}`.

**Why:** All questions sent in one parallel request; state stays compact (< 2k chars) for best accuracy.

**How to apply:** When adding to or modifying `stage_agent`, maintain this flat-battery pattern. Company list goes into the `instructions` text of a single Noul, not as separate questions. Rejection reason is diagnosed by Jev itself via Choice.

Related: [[jev-state-size-accuracy]], [[project_v2_architecture]]

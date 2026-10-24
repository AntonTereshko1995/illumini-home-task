---
name: jev-state-size-accuracy
description: Empirical data on Jev accuracy degradation vs. state size — keep state under 2000 chars for best results
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d843f2ef-4cf3-42f4-a402-c7d79ac702a5
---

State size significantly impacts Jev accuracy (average over 2 runs):

| Filler chars | Beginning | Middle | End |
|-------------|-----------|--------|-----|
| 0 (base)    | 96.8%     | —      | —   |
| 700         | 94.1%     | 92.0%  | 92.1% |
| 2 000       | 93.2%     | 90.4%  | 92.7% |
| 10 000      | 91.6%     | 91.4%  | 93.0% |
| 40 000      | 91.1%     | 90.0%  | 91.4% |
| 145 000     | 91.8%     | 88.4%  | 91.8% |

**Rule: keep state under 2 000 characters for best accuracy.**

**Why:** Jev accuracy drops ~4–6pp when state grows from 0 to 2k chars; beyond 2k the degradation is more gradual but meaningful (up to ~8pp at 145k). The user measured this empirically on their own data.

**How to apply:** When building jev state for `stage_agent`, do NOT include `page_visible_text` or other large fields. Use only compact, resolved fields: `company`, `title`, `location_strings`, `is_remote`, `title_tag`, `url`. Truncate any text field that pushes state over ~1500 chars.

Related: [[project_v2_architecture]], [[jev-implementation-pattern]]

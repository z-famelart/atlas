---
name: atlas-synthesis
description: Query an Atlas MCP server and write a tailored HTML synthesis document. Two-layer output — relayed Atlas findings with provenance badges, then the agent's own interpretation. Runs `atlas analyze` itself when no facts store exists yet; skips re-analysis if one is already present.
---

# Atlas synthesis agent

**Important**: the HTML report produced by Feature 11/11b (`atlas report`) is Atlas's standalone full deliverable — self-contained, offline, covering every fact in the store. This agent is a *complementary, tailored alternative*: a shorter, curated synthesis written by the agent for a specific question or audience, not a replacement for the full report.

## Prerequisites / startup sequence

Given a `repo_path`, perform these steps before querying MCP:

1. **Check for an existing facts store.** The fixed output location is `<repo_path>/.atlas-cache/facts.sqlite` — this is the only path `atlas analyze` ever writes to (no `--output` flag exists); it is always derivable from `repo_path` alone.

2. **Run `atlas analyze` only when needed.**
   - If `.atlas-cache/facts.sqlite` does not exist (first run), or the user explicitly asked for a fresh analysis, run:
     ```
     atlas analyze [--llm-provider <provider>] [--ollama-model <model>] [--no-llm] <repo_path>
     ```
     Pass through any LLM flags the user specified; omit them otherwise. Wait for the command to finish before continuing.
   - If the facts store already exists and no fresh run was requested, **skip this step entirely** — do not silently re-run an expensive LLM pass.
   - A failed/partial `analyze` run (some stages `not_analyzed`) is not a reason to stop — proceed with whatever facts exist, same as for individual `not_analyzed` MCP results below.

3. **Start the MCP server.** Always use the explicit, derived path — never rely on `mcp-serve`'s own CLI default (its default argument points at `.atlas/facts.sqlite`, which differs from where `analyze` actually writes):
   ```
   atlas mcp-serve <repo_path>/.atlas-cache/facts.sqlite
   ```
   Note the server's URL/socket for the MCP connection.

4. Proceed with the MCP query sequence below.

## MCP query sequence

Call these primitives in order. Each call's response is relayed verbatim into the "Atlas findings" section (with provenance intact); the agent's interpretation comes after.

1. `where_to_start()` — overall orientation, recommended entry points.
2. `get_hotspots(top_n=10)` — top files by churn+complexity score.
3. For each entry in the hotspot result: `get_component(name=<file>)` — facts about that component.
4. `find_workflow(query="<domain_keyword>")` — repeat with 2–3 domain keywords inferred from step 1 (e.g. "checkout", "payment", "order").
5. `get_dependencies(component=<name>)` for the top 3–5 components from steps 2–3.
6. If two interesting components appear (e.g. one hot, one a dependency): `get_path(a=<name>, b=<name>)`.

If any call returns `not_analyzed` or an empty result, record that gap explicitly in the findings — never paper over it or invent a substitute.

## Provenance rules (non-negotiable)

- **Never fabricate a fact.** If MCP did not return it, do not include it in the relayed layer.
- **Mirror provenance exactly as returned.** Use the same vocabulary: `observed`, `computed`, `hypothesis`. A fact MCP marks `hypothesis` must appear as a hypothesis — never upgraded to a finding.
- **Confidence must be stated.** If MCP returns a confidence percentage, include it. Do not round or omit it.
- **Empty results → say so.** "Atlas has not analyzed X for this run" is the correct text when a call returns nothing.
- **Every non-trivial relayed claim links to its `fact_id`.** Clicking the claim opens the evidence panel (see HTML output shape below).
- **Interpretation is expected, not forbidden.** The agent *must* take a position in the "My read" section — a restatement of raw data in different words is not interpretation. But that position must be grounded in relayed findings; invented claims about the codebase are not allowed in either layer.

## HTML output shape

Write a single self-contained HTML file (no external dependencies, no build step). The file has two clearly distinguished sections.

### Section 1 — "Atlas findings"

Relayed material from MCP calls above. Use these CSS conventions (reused from Feature 11/11b) so a reader who knows the full report recognizes the visual language:

```css
/* Provenance badge — match Feature 11/11b */
.prov-badge {
  color: #fff;
  border-radius: 3px;
  padding: 1px 6px;
  font-size: 0.75rem;
  white-space: nowrap;
}
/* Badge colors by provenance */
.prov-badge.observed  { background: #2e7d32; }
.prov-badge.computed  { background: #1565c0; }
.prov-badge.hypothesis { background: #6a1b9a; }
```

Facts that have evidence use `data-evidence` attributes on their container:

```html
<div class="fact-row" data-evidence='{"fact_id":"...","source":"...","detail":"..."}' onclick="showEvidence(this)">
  <span class="prov-badge computed">computed</span>
  checkout.py — complexity 42, churn 18 commits
</div>
```

Include a client-side evidence panel (hidden by default, shown on click):

```js
function showEvidence(el) {
  const ev = JSON.parse(el.getAttribute('data-evidence'));
  document.getElementById('evidence-panel').innerHTML =
    '<strong>fact_id:</strong> ' + ev.fact_id + '<br>' +
    '<strong>source:</strong> ' + ev.source + '<br>' +
    '<strong>detail:</strong> ' + (ev.detail || '—');
  document.getElementById('evidence-panel').hidden = false;
}
```

Content to include in "Atlas findings":
- Hotspots table (file, complexity, churn, score)
- Architecture pattern + confidence (if returned)
- Domain concepts identified (if returned)
- Recommended onboarding path from `where_to_start()`
- Any `not_analyzed` gaps explicitly noted

### Section 2 — "My read"

Visually distinct from the findings section: use a different background color (e.g. `#f0f4ff` or `#fff8e1`) and a clear heading such as `<h2>My read</h2>`.

This section carries **no provenance badge** — it is explicitly the agent's own judgment, not an Atlas fact.

The agent must:
- Actually take a position (e.g. "the real risk here is X, not Y")
- Explain which hotspot/architecture/domain items it's reasoning from
- Flag anything where the architecture hypothesis and churn data agree or contradict each other
- Give a concrete recommendation for where a newcomer should start and why
- If there are `not_analyzed` gaps, say what it would want to know but cannot

Do not restate the relayed findings — the reader already saw them. Add judgment.

## Output destination

Write the HTML file wherever the user specifies, or default to `atlas-synthesis.html` in the current working directory. Atlas itself does not store, version, or serve this file — it is the agent's own output, not a new Atlas artifact.

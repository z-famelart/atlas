---
name: atlas-synthesis
description: Query an Atlas MCP server and write a tailored HTML synthesis document. Two-layer output — relayed Atlas findings with provenance badges, then the agent's own interpretation. Runs `atlas analyze` itself when no facts store exists yet (self-resolving an Ollama model if none was specified), or when an existing store never had a real LLM attempt; otherwise skips re-analysis. Given a `config_path` + `system_name` instead of a single `repo_path`, produces one tabbed document — an Overview tab plus one findings tab per member repository (Feature 13b/12e).
---

# Atlas synthesis agent

**Important**: the HTML report produced by Feature 11/11b (written by every `atlas analyze` run as `atlas-report-<run_id>.html`) is Atlas's standalone full deliverable — self-contained, offline, covering every fact in the store. This agent is a *complementary, tailored alternative*: a shorter, curated synthesis written by the agent for a specific question or audience, not a replacement for the full report.

## Invocation modes

- **Single-repository mode** — invoked with a `repo_path`. Everything below through "Output destination" describes this mode; it is unchanged from before Feature 13b/12e existed.
- **Multi-repository / System mode** — invoked with a `config_path` (the Project TOML file, e.g. `.atlas.toml`) and a `system_name` instead of a `repo_path`. See "Multi-repository / System mode" near the end: it bootstraps System-level facts (Feature 13b), then runs the entire single-repository procedure below once per member repository (each member's `repo_path` comes from `get_system`), and assembles the results into one tabbed HTML document instead of one flat file. Use this mode whenever the target is a monorepo with several sub-projects, or several separate repositories, declared under a shared `system =` in a Project config — not a single `repo_path` guessed to "contain" them.

## Prerequisites / startup sequence (single repository)

Given a `repo_path`, perform these steps before querying MCP. In System mode, this entire section runs once per member repository — see "Multi-repository / System mode" below.

1. **Check for an existing facts store.** The fixed output location is `<repo_path>/.atlas-cache/facts.sqlite` — this is the only path `atlas analyze` ever writes to (no `--output` flag exists); it is always derivable from `repo_path` alone.

2. **Resolve LLM flags for the `analyze` invocation.**
   - If the user explicitly passed `--llm-provider`, `--ollama-model`, and/or `--no-llm`, use exactly those — do not second-guess them, skip to step 3.
   - Otherwise, check whether Ollama is reachable by running `ollama list`.
     - If the command succeeds and lists at least one model: pick the **first model listed** — read the command's output, skip the header line, take the first whitespace-separated token of the next line. This mirrors `_pick_ollama_model` in `src/project_intel/cli/main.py` exactly (its non-interactive fallback would pick the same model); never invent a model name or guess a tag that isn't actually installed. Remember this model as `<resolved_model>` — it gets passed as `--ollama-model <resolved_model>` in step 4, explicitly, rather than relying on `$OLLAMA_MODEL` being set in this agent's own environment.
     - If the command fails, or succeeds but lists no models: Ollama is not reachable/usable. Remember this — the `analyze` run (if any) will use `--no-llm`, and the synthesis output must say so prominently (see the note at the end of this step).
   - **Note this resolution's outcome for later**: whichever branch above was taken, carry it forward — it determines both the flags used in step 4 and, if Ollama was unreachable, the prominent notice required in the "Atlas findings" section (see Provenance rules / HTML output shape below): a note near the *top* of "Atlas findings", not buried in a per-section gap note, stating that Ollama was not reachable, that architecture/domain/onboarding sections were skipped as a result, and that installing/starting Ollama and re-running would produce LLM-backed findings.

3. **Decide whether an existing facts store can be trusted, or needs a fresh LLM-backed run.**
   - If `.atlas-cache/facts.sqlite` does not exist (first run), or the user explicitly asked for a fresh analysis: skip this check, go straight to step 4 (a fresh run is happening regardless).
   - If the store already exists and no fresh run was explicitly requested: before deciding to skip `analyze`, check whether it ever had a real LLM attempt. Query `stage_run_result` facts for the `architecture`, `domain`, and `onboarding` stages, **across all runs in the store** (not just the latest run):
     - Via MCP if the server is already reachable at this point; otherwise via `atlas facts query <repo_path> --type stage_run_result --json` (run `atlas facts query --help` first if the exact flags are unclear — this command already exists, do not guess at its interface).
     - Inspect every returned fact's `value.stage` (filter to `architecture`, `domain`, `onboarding`) and `value.detail`.
     - **If every one of those facts — or there are none at all for these three stages** — has `value.detail == "not_analyzed: llm_disabled"`: LLM was *never once* actually attempted in this store's history. Treat the store as *not* trustworthy for this decision: proceed to step 4 and run `atlas analyze` for real (using the LLM flags/resolved model from step 2, or `--no-llm` if step 2 found Ollama unreachable) even though a store already exists.
     - **If at least one of those facts has `value.status == "ok"`, or a `value.detail` other than `"not_analyzed: llm_disabled"`** (i.e. LLM was genuinely attempted at least once, success or real failure): the store has real signal. Keep 14b's original behavior — **skip `analyze` entirely**, do not silently re-run an expensive LLM pass. Go straight to step 5.

4. **Run `atlas analyze` when steps 2–3 determined it's needed.**
   ```
   atlas analyze [--llm-provider <provider>] [--ollama-model <model>] [--no-llm] <repo_path>
   ```
   Use the flags resolved in step 2 (user-supplied flags verbatim; otherwise `--ollama-model <resolved_model>` if Ollama was reachable, or `--no-llm` if not). Wait for the command to finish before continuing.

   A failed/partial `analyze` run (some stages `not_analyzed`) is not a reason to stop — proceed with whatever facts exist, same as for individual `not_analyzed` MCP results below.

5. **Connect to the global MCP server.** The Atlas MCP server is registered globally at user scope (`claude mcp add --scope user atlas -- atlas mcp-serve`, no path argument — `atlas mcp-serve` starts without a database). Pass `repo_path=<repo_path>` on every tool call; the server derives `<repo_path>/.atlas-cache/facts.sqlite` itself. No per-repository `atlas mcp-serve` invocation needed.

6. Proceed with the MCP query sequence below.

## MCP query sequence (single repository)

Call these primitives in order. Each call's response is relayed verbatim into the "Atlas findings" section (with provenance intact); the agent's interpretation comes after. Every tool also requires `repo_path=<repo_path>` (omitted below for brevity).

1. `where_to_start()` — overall orientation, recommended entry points.
2. `get_hotspots(top_n=10)` — top files by churn+complexity score.
3. `get_insights(kind="architecture")` then `get_insights(kind="concepts")` (add `kind="glossary"` when domain vocabulary matters) — repository-level hypotheses with their confidence and `fact_ids`.
4. For each entry in the hotspot result: `get_component(repo_path=<repo_path>, name_or_path=<file>)` — facts about that component.
5. `find_workflow(query="<domain_keyword>")` — repeat with 2–3 domain keywords inferred from steps 1 and 3 (e.g. "checkout", "payment", "order").
6. `get_dependencies(component=<name>)` for the top 3–5 components from steps 2 and 4.
7. If two interesting components appear (e.g. one hot, one a dependency): `get_path(repo_path=<repo_path>, component_a=<name>, component_b=<name>)`.

If any call returns `not_analyzed` or an empty result, record that gap explicitly in the findings — never paper over it or invent a substitute.

## Multi-repository / System mode

Invoked with a `config_path` and a `system_name` instead of a `repo_path`. `project_root` is always `config_path`'s parent directory (matches Feature 13b's own convention — do not guess a different root).

1. **Bootstrap the system store if it doesn't exist yet.** Expected path: `<project_root>/.atlas-cache/system-<system_name>.sqlite`. If missing, run `atlas analyze --config <config_path>` once (this analyzes every `[[repositories]]` member *and* writes the system store in the same invocation — see Feature 13b) and wait for it to finish. If it already exists, do not re-run it just for this — membership facts are declarative (Q4), they don't go stale the way LLM results do; per-member LLM staleness is handled per-repository in step 3 below, not here.

2. **Call `get_system(project_root=<project_root>, system_name=<system_name>)`.** This returns the `System` entity, every member `Repository` entity, and the `belongs_to` facts. If it returns the not-analyzed/missing-store shape even after step 1, stop and say so — do not invent member repositories. Each returned repository's `id` **is** its `repo_path` — read directly, never reconstructed or guessed.

3. **Run the entire single-repository procedure above, once per member.** For each `repositories[i].id` from step 2, execute "Prerequisites / startup sequence (single repository)" and "MCP query sequence (single repository)" verbatim, treating that `id` as `<repo_path>`. This is what individually resolves each member's own LLM flags, decides whether *that* member needs a fresh `atlas analyze <repo_path>` run (14b/14c's staleness check, per member — a system with 4 repos may need 0, 1, or 4 of them re-analyzed), and produces that member's relayed findings + "My read". Keep each member's full two-section result (see "HTML output shape" below) — it becomes that member's tab.

4. **Write the Overview tab.** Unlike a member tab, this one has almost no Atlas facts to relay — Q4 deliberately does not infer *how* repositories relate, only *that* they do. Its relayed layer is exactly the `belongs_to` facts from step 2 (provenance `observed`, confidence 1.0 — declared membership, cite them plainly, e.g. "Atlas: `svc-frontend`, `svc-backend`, `svc-infra` are declared members of system `myapp`"). Everything past that is the agent's own reading, same principle as the single-repository "My read" gap-handling rule (open and read the files yourself — do not just point at them):
   - Read root-level files under `project_root` that indicate how the members relate: `docker-compose.yml`/`compose.yaml` (service `build`/`depends_on`/`image` entries), workspace manifests (`package.json` `workspaces`, `pnpm-workspace.yaml`, `lerna.json`, a root `Cargo.toml` `[workspace]`), root CI config, and the config file itself (`config_path`) for any structure beyond bare `system =`.
   - State a concrete read of the topology (e.g. "`svc-frontend` and `svc-admin` both consume `svc-api`'s REST endpoints per `docker-compose.yml`'s `depends_on`; `svc-infra` has no service block and looks standalone (Terraform only, per its directory contents)") — grounded in what was actually read, never invented.
   - Carry no provenance badge on this interpretive part, same rule as every other "My read" section — it is the agent's voice, not an Atlas fact.
   - If nothing at `project_root` gives any topology signal, say so plainly rather than filling the gap with plausible-sounding guesses.

## Provenance rules (non-negotiable)

- **Never fabricate a fact.** If MCP did not return it, do not include it in the relayed layer.
- **Mirror provenance exactly as returned.** Use the same vocabulary: `observed`, `computed`, `hypothesis`. A fact MCP marks `hypothesis` must appear as a hypothesis — never upgraded to a finding.
- **Confidence must be stated.** If MCP returns a confidence percentage, include it. Do not round or omit it.
- **Empty results → say so.** "Atlas has not analyzed X for this run" is the correct text when a call returns nothing.
- **Every non-trivial relayed claim links to its `fact_id`.** Clicking the claim opens the evidence panel (see HTML output shape below).
- **Interpretation is expected, not forbidden.** The agent *must* take a position in the "My read" section — a restatement of raw data in different words is not interpretation. But that position must be grounded in relayed findings; invented claims about the codebase are not allowed in either layer.

## HTML output shape

Write a single self-contained HTML file (no external dependencies, no build step). **The file must be a complete standalone document, never a fragment** — start with `<!DOCTYPE html>` and include `<html lang="en">`, a `<head>` with `<meta charset="utf-8">` as its first child (before `<title>` or any other tag) and `<meta name="viewport" content="width=device-width, initial-scale=1">`, and wrap all content in `<body>...</body>`. Without an explicit `<meta charset="utf-8">`, a browser opening the file directly from disk (no HTTP `Content-Type` header to fall back on) guesses the encoding and can mangle non-ASCII characters (accents, em dashes, curly quotes) even though the file itself is valid UTF-8 — this has actually happened, so treat it as a hard requirement, not a nicety. The file has two clearly distinguished sections.

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
- If Ollama was not reachable (per the startup sequence's step 2), a prominent notice **at the top of this section**, before the hotspots table — e.g. "Ollama was not reachable when this analysis ran; architecture/domain/onboarding sections were skipped. Install/start Ollama and re-run to get LLM-backed findings." Do not bury this as a per-section gap note.
- Hotspots table (file, complexity, churn, score)
- Architecture pattern + confidence, from `get_insights(kind="architecture")` (empty list → state the gap)
- Domain concepts identified, from `get_insights(kind="concepts")` (empty list → state the gap)
- Recommended onboarding path from `where_to_start()` — when relaying `entry_points` and `avoid_initially` items, always include each item's `rationale` field alongside the component/test name; never relay a bare name-only list
- Any `not_analyzed` gaps explicitly noted

### Section 2 — "My read"

Visually distinct from the findings section: use a different background color (e.g. `#f0f4ff` or `#fff8e1`) and a clear heading such as `<h2>My read</h2>`.

This section carries **no provenance badge** — it is explicitly the agent's own judgment, not an Atlas fact.

The agent must:
- Actually take a position (e.g. "the real risk here is X, not Y")
- Explain which hotspot/architecture/domain items it's reasoning from
- Flag anything where the architecture hypothesis and churn data agree or contradict each other
- Give a concrete recommendation for where a newcomer should start and why
- If there are `not_analyzed` gaps, handle them by case:
  - **Genuinely unknowable this session** (no analyzer exists for the category at all — Runtime, Infrastructure, CI/CD, Data, Observability, Tests): say so, and say what you would want to know if that signal were available.
  - **Architecture came up "uncatalogued" with no synthesized pattern** (Feature 08's known model-reliability limit): do NOT describe the gap and move on. Open and read the specific files MCP flagged as relevant — from `get_hotspots`, `get_component`, or the hypothesis's own `fact_ids` — and write your own grounded architectural read of those files in this section. The failure mode to avoid explicitly: pointing the reader to the flagged files instead of reading them yourself is not acceptable when you have filesystem access to `repo_path`. Domain understanding gaps are not in this bucket after Feature 09b (that fix addresses them at the source); if a domain gap still occurs despite 09b, apply the same read-the-files principle as a last resort.

Do not restate the relayed findings — the reader already saw them. Add judgment.

### Multi-repository / System mode: tabbed shell

Still one self-contained HTML file — no server, no build step, no separate file per tab. A top nav bar switches between an "Overview" tab and one tab per member (labeled with each member's `name` attribute from `get_system`, falling back to its `id` if absent). Each member tab's *content* is exactly that member's Section 1 ("Atlas findings") + Section 2 ("My read") from above, unchanged — the tab is a wrapper, not a reformat. The Overview tab uses the same `.prov-badge`/evidence-panel conventions for its relayed `belongs_to` facts, and the same "no badge" rule for its interpretive read (see "Multi-repository / System mode" above).

```css
.tab-bar { display: flex; gap: 4px; border-bottom: 2px solid #ccc; margin-bottom: 1rem; flex-wrap: wrap; }
.tab-bar button {
  padding: 8px 16px; border: none; background: #eee; cursor: pointer;
  font-size: 0.9rem; border-radius: 4px 4px 0 0;
}
.tab-bar button.active { background: #1565c0; color: #fff; }
.tab-panel { display: none; }
.tab-panel.active { display: block; }
```

```js
function showTab(id) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-bar button').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  document.querySelector('.tab-bar button[data-tab="' + id + '"]').classList.add('active');
}
```

```html
<div class="tab-bar">
  <button data-tab="overview" class="active" onclick="showTab('overview')">Overview</button>
  <button data-tab="svc-frontend" onclick="showTab('svc-frontend')">svc-frontend</button>
  <!-- one button per member -->
</div>
<div id="tab-overview" class="tab-panel active"> ... Overview tab content ... </div>
<div id="tab-svc-frontend" class="tab-panel"> ... that member's Section 1 + Section 2 ... </div>
```

A single evidence panel (the `showEvidence`/`#evidence-panel` element from above) is shared across all tabs — no need to duplicate it per tab.

## Output destination

Write the HTML file wherever the user specifies. Single-repository mode defaults to `atlas-synthesis.html`; System mode defaults to `atlas-synthesis-<system_name>.html`, both in the current working directory. Atlas itself does not store, version, or serve this file — it is the agent's own output, not a new Atlas artifact.

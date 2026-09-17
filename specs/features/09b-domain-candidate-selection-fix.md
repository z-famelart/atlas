# Feature 09b — Fix candidate selection: the `top_n` budget doesn't actually bound the prompt, and coverage is never requested

## Why this is a separate feature, not a rewrite of Feature 09

Feature 09 is **already implemented**. This feature fixes concrete, evidence-backed defects in `domain/selector.py` and `domain/analyzer.py` found by replaying `select_candidates` directly against a real `FactStore` (crewlybase, 165 scored files) — not by changing `DomainResponse`/`BusinessConcept`/`BusinessWorkflow`/`GlossaryTerm`'s shape (`domain/schema.py`), which is unchanged.

## Why this is the right place to fix this, not the `atlas-synthesis` agent

An earlier diagnosis this session wrongly targeted [Feature 14d](14d-agent-grounds-interpretation-in-own-reading.md) (the synthesis agent reading source files itself) as the fix for thin domain output. Per direct correction: Atlas's own `domain_understanding` stage is the thing that should produce good domain concepts directly — a coding agent compensating by reading the repo itself is, at best, a defensive fallback for a tool limitation, not an acceptable substitute for the tool doing its job. This feature is the actual fix; 14d stays scoped to its own narrower, legitimate purpose (relaying `rationale` fields already present in facts, and not confusing "no analyzer exists" with "Atlas's stage came up thin" in the one specific case where reading really is the only option left).

## What was actually found (grounding for this spec)

Replayed `select_candidates`'s exact logic against crewlybase's real `FactStore` (single run, 165 `hotspot_score` facts):

1. **The `top_n` budget only bounds step 1.** `select_candidates`'s docstring calls its return value "a bounded candidate set", and step 2's own comment says "Cap entrypoints to top_n so the total stays bounded" — but the code caps *the entrypoints list itself* to `top_n` (`list(entrypoints.items())[:top_n]`), not the running total already in `top_files`. Step 3 adds more on top with no cap at all. Measured: **20 → 38 → 42** candidates after steps 1/2/3 respectively — more than double the documented/intended 20.
2. **Step 3's "test file" match is far broader than its own docstring claims.** `"Test files: name-match to selected source files"` describes the intent, but `is_workflow_test = any(kw in path.lower() for kw in _WORKFLOW_KEYWORDS)` matches *any* path containing `"workflow"`, `"process"`, `"service"`, `"domain"`, `"handler"`, or `"controller"` — with no check that the file is actually a test. Measured false positive: `.github/workflows/ci.yml` was added as a "test file" candidate solely because `"workflow"` appears in its path.
3. **The actual domain output only engaged with 2 of the 42 candidates.** The stored `business_concept`/`business_workflow`/`glossary_term` facts (4 total) cite exactly two source `fact_ids`, tracing back to `festivals/services/team.py` and `accounts/services.py` — despite `applications/services.py`, `scheduling/services.py`, `festivals/services/core.py`, and `journal/services.py` (real, domain-bearing files) all being present in the candidate set sent to the model. The prompt (`domain/analyzer.py`'s `_INSTRUCTIONS`) never asks the model to examine every candidate or cover multiple modules — nothing pushes a weaker local model (qwen2.5-coder, this run) past whichever file it engages with first.
4. **`select_candidates` queries `hotspot_score`/`centrality` with no `run_id` filter** (`store.query_facts(type="hotspot_score")`, no `run_id=` argument) — same bug class already fixed for the HTML report (Q140d/11c) and MCP (Q154f/12c), just never applied here. Didn't manifest in this single-run store, but on a repository with several accumulated `analyze` runs it reintroduces the same duplication/dilution risk.

Together: the model was handed roughly double the intended, already-generous candidate budget, padded with at least one outright irrelevant file, with no instruction to actually use more than a sliver of it — and it used a sliver. This is a genuine content-generation gap in Feature 09 itself, not a rendering or relay problem.

## Depends on

Feature 09 (domain understanding — already implemented, this feature changes `domain/selector.py`'s `select_candidates` and `domain/analyzer.py`'s `_INSTRUCTIONS` only; `DomainResponse` and its component dataclasses are unchanged).

## Scope

### A. Make `top_n` a real cumulative budget

`select_candidates` stops adding candidates once `len(top_files) >= top_n`, across all three steps combined, not just step 1. Priority order stays hotspot → entrypoint → test (steps run in the same order as today; each step now checks the remaining budget before adding, rather than adding unconditionally and only capping its own local list).

### B. `is_workflow_test` requires an actual test-file signal

Add a real test-file check (reuse the already-existing `_TEST_STEM_RE`/`_test_base` machinery, or a path check for a `tests/`/`test_` component) as a precondition — a file only qualifies via the workflow-keyword path if it's already identified as a test file by name/path convention. A non-test file that happens to contain `"service"` or `"workflow"` in its path (i.e. almost every backend module in a services-oriented codebase) is no longer swept in by this step; it's still eligible via step 1 (hotspot score) on its own merits, same as today.

### C. Prompt requires explicit coverage across candidates

Strengthen `_INSTRUCTIONS` (`domain/analyzer.py`) with an explicit coverage instruction, e.g.: *"Examine every file provided below, not just the first one or two that stand out — a repository with several distinct modules/apps should produce concepts, workflows, and glossary terms spanning more than one of them whenever the evidence supports it. Do not stop once you've found one concept if other candidate files describe unrelated domain logic."*

### D. Scope candidate queries to the current run

`select_candidates`'s `hotspot_score`/`centrality` queries pass `run_id` (the same two-step "current run, else most recent" fallback already used elsewhere is unnecessary here — this function has no report-facing fallback narrative to produce; it's an internal candidate-selection input, so a hard filter to the run being analyzed is enough, matching how `collect_input_facts` already scopes other Feature 09/10 input gathering per-run where applicable).

## Explicitly out of scope for this feature

- `DomainResponse`/`BusinessConcept`/`BusinessWorkflow`/`GlossaryTerm`'s shape — unchanged.
- Feature 07's citation validator, caching, or budget mechanics — this feature only changes which files are candidates and how the prompt asks the model to use them.
- A token/character budget on the *total* prompt size (Q86, still **Ouvert**) — this feature fixes `top_n` actually meaning `top_n`, it doesn't introduce a new, separate token-level cap; if `top_n` files at up to 4000 chars each is still too large for a given provider, that's Q86's still-open scope, not this feature's.
- [Feature 14d](14d-agent-grounds-interpretation-in-own-reading.md)'s "My read" grounding-in-own-reading behavior — stays as a narrower defensive fallback for the case Atlas genuinely cannot help (e.g. a category with no analyzer at all), not superseded by this feature, but no longer the primary mitigation for domain-concept poverty now that this feature fixes the actual cause.

## Acceptance criteria

- A fixture `FactStore` with hotspot facts producing 20 step-1 candidates, 15 additional entrypoint candidates, and several test-named candidates all matching workflow keywords: `select_candidates(top_n=20)` returns **exactly 20** candidates (or fewer if fewer exist), never more — regardless of how many entrypoints/test matches exist.
- A fixture with a non-test file whose path contains `"service"` (e.g. `apps/accounts/services.py`, already selected via step 1) and a genuinely irrelevant non-test file whose path contains `"workflow"` (e.g. `.github/workflows/ci.yml`) confirms the latter is never added by step 3.
- A fixture with a real test file (`tests/festivals/test_services.py`) whose stem matches a selected source file's stem is still added by step 3, unchanged from today's intent.
- `build_prompt`'s output (asserted via a test) includes the new explicit multi-file coverage instruction.
- A fixture with `hotspot_score`/`centrality` facts under two different `run_id`s: `select_candidates` for a given `run_id` only considers that run's facts.
- `uv run pytest` and `uv run ruff check .` pass.

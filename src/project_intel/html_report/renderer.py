"""HTML report renderer — produces a single self-contained offline HTML file."""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from project_intel.facts.model import Fact
from project_intel.facts.store import FactStore

# ---------------------------------------------------------------------------
# Shared rendering primitives
# ---------------------------------------------------------------------------

_PROVENANCE_COLORS = {
    "observed": "#2e7d32",
    "computed": "#1565c0",
    "inferred": "#e65100",
    "hypothesis": "#6a1b9a",
}


def _badge(provenance: str, confidence: float) -> str:
    color = _PROVENANCE_COLORS.get(provenance, "#555")
    pct = int(confidence * 100)
    return (
        f'<span class="prov-badge" style="background:{color}" title="confidence {pct}%">'
        f'{provenance}</span>'
        f'<span class="conf-bar"><span class="conf-fill" style="width:{pct}%"></span></span>'
    )


def _evidence_json(fact: Fact) -> str:
    evs = []
    for ev in fact.evidence:
        d: dict[str, Any] = {
            "kind": ev.kind,
            "source_analyzer": ev.source_analyzer,
            "retrieved_at": ev.retrieved_at.isoformat(),
        }
        d.update(dataclasses.asdict(ev.ref))
        evs.append(d)
    return json.dumps(evs, ensure_ascii=False)


def _fact_row(label: str, fact: Fact) -> str:
    ev = _evidence_json(fact)
    badge = _badge(fact.provenance, fact.confidence)
    return (
        f'<div class="fact-row" data-evidence=\'{ev}\' onclick="showEvidence(this)">'
        f'<span class="fact-label">{_esc(label)}</span> {badge}'
        f'</div>'
    )


def _not_analyzed(section: str) -> str:
    return f'<p class="not-analyzed">Not analyzed — no {section} facts in this run.</p>'


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _section(title: str, body: str, section_id: str) -> str:
    return (
        f'<section id="{section_id}">'
        f'<h2>{_esc(title)}</h2>'
        f'{body}'
        f'</section>'
    )


def _render_executive_summary(store: FactStore, run_id: str) -> str:
    langs = list(store.query_facts(type="language_detected", run_id=run_id))
    techs = list(store.query_facts(type="technology_detected", run_id=run_id))
    repos = list(store.query_facts(type="git_repository_detected", run_id=run_id))

    if not langs and not techs and not repos:
        return _section("Executive Summary", _not_analyzed("discovery"), "executive-summary")

    rows = []
    for f in repos:
        rows.append(_fact_row(f"Repository: {f.subject.id}", f))
    for f in langs:
        name = (f.value or {}).get("language", f.subject.id)
        rows.append(_fact_row(f"Language: {name}", f))
    for f in techs:
        name = (f.value or {}).get("technology", f.subject.id)
        rows.append(_fact_row(f"Technology: {name}", f))

    body = '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Executive Summary", body, "executive-summary")


def _render_system_map(store: FactStore, run_id: str) -> str:
    centrality = list(store.query_facts(type="centrality", run_id=run_id))
    if not centrality:
        return _section("System Map", _not_analyzed("code-graph"), "system-map")

    top = sorted(centrality, key=lambda f: float((f.value or {}).get("score", 0)), reverse=True)[:20]
    mermaid = "graph LR\n" + "\n".join(f"  {_esc(f.subject.id.split('/')[-1])}[{_esc(f.subject.id.split('/')[-1])}]" for f in top[:10])
    rows = [_fact_row(f.subject.id, f) for f in top]
    body = (
        f'<pre class="mermaid">{mermaid}</pre>'
        f'<p class="mermaid-hint">Load mermaid.js locally to render diagram.</p>'
        f'<div class="fact-list">{"".join(rows)}</div>'
    )
    return _section("System Map", body, "system-map")


def _render_architecture(store: FactStore, run_id: str) -> str:
    facts = list(store.query_facts(type="architecture_hypothesis", run_id=run_id))
    if not facts:
        return _section("Architecture", _not_analyzed("architecture_hypothesis"), "architecture")

    rows = []
    for f in facts:
        label = (f.value or {}).get("pattern", f.subject.id)
        rows.append(_fact_row(str(label), f))
    body = '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Architecture", body, "architecture")


def _render_code_map(store: FactStore, run_id: str) -> str:
    symbols = list(store.query_facts(type="symbol_defined", run_id=run_id))
    communities = list(store.query_facts(type="community", run_id=run_id))
    if not symbols and not communities:
        return _section("Code Map", _not_analyzed("code-graph"), "code-map")

    rows = []
    for f in communities[:30]:
        label = f"Community {(f.value or {}).get('community_id', f.subject.id)}"
        rows.append(_fact_row(label, f))
    for f in symbols[:30]:
        rows.append(_fact_row(f.subject.id, f))
    body = '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Code Map", body, "code-map")


def _render_hotspots(store: FactStore, run_id: str) -> str:
    facts = list(store.query_facts(type="hotspot_score", run_id=run_id))
    if not facts:
        return _section("Hotspots", _not_analyzed("hotspot_score"), "hotspots")

    top = sorted(facts, key=lambda f: float((f.value or {}).get("score", 0)), reverse=True)[:30]
    rows = [
        _fact_row(
            f"{f.subject.id} (score: {float((f.value or {}).get('score', 0)):.2f})",
            f,
        )
        for f in top
    ]
    body = '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Hotspots", body, "hotspots")


def _render_domain(store: FactStore, run_id: str) -> str:
    concepts = list(store.query_facts(type="business_concept", run_id=run_id))
    workflows = list(store.query_facts(type="business_workflow", run_id=run_id))
    if not concepts and not workflows:
        return _section("Domain Understanding", _not_analyzed("domain"), "domain-understanding")

    rows = []
    for f in concepts:
        name = (f.value or {}).get("name", f.subject.id)
        rows.append(_fact_row(f"Concept: {name}", f))
    for f in workflows:
        name = (f.value or {}).get("name", f.subject.id)
        rows.append(_fact_row(f"Workflow: {name}", f))
    body = '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Domain Understanding", body, "domain-understanding")


def _not_analyzed_section(title: str, section_id: str) -> str:
    return _section(title, _not_analyzed(section_id.replace("-", "_")), section_id)


def _render_git_evolution(store: FactStore, run_id: str) -> str:
    churn = list(store.query_facts(type="git_churn", run_id=run_id))
    cochange = list(store.query_facts(type="git_co_change", run_id=run_id))
    if not churn and not cochange:
        return _section("Git Evolution", _not_analyzed("git_churn"), "git-evolution")

    top_churn = sorted(churn, key=lambda f: int((f.value or {}).get("commits", 0)), reverse=True)[:20]
    rows = [_fact_row(f"{f.subject.id} ({(f.value or {}).get('commits', '?')} commits)", f) for f in top_churn]
    for f in cochange[:10]:
        label = f"Co-change: {f.subject.id} ↔ {f.object.id if f.object else '?'}"
        rows.append(_fact_row(label, f))
    body = '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Git Evolution", body, "git-evolution")


def _render_risks(store: FactStore, run_id: str) -> str:
    cycles = list(store.query_facts(type="dependency_cycle", run_id=run_id))
    if not cycles:
        return _section("Risks / Anomalies", _not_analyzed("dependency_cycle"), "risks-anomalies")

    rows = [_fact_row(f"Dependency cycle: {f.subject.id}", f) for f in cycles]
    body = '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Risks / Anomalies", body, "risks-anomalies")


def _render_glossary(store: FactStore, run_id: str) -> str:
    terms = list(store.query_facts(type="glossary_term", run_id=run_id))
    if not terms:
        return _section("Glossary", _not_analyzed("glossary_term"), "glossary")

    rows = []
    for f in terms:
        term = (f.value or {}).get("term", f.subject.id)
        definition = (f.value or {}).get("definition", "")
        rows.append(_fact_row(f"{term}: {definition}", f))
    body = '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Glossary", body, "glossary")


def _render_evidence(store: FactStore, run_id: str) -> str:
    all_facts = list(store.query_facts(run_id=run_id))
    if not all_facts:
        return _section("Evidence", _not_analyzed("evidence"), "evidence")

    rows = [_fact_row(f"[{f.type}] {f.subject.id}", f) for f in all_facts[:100]]
    note = f'<p>{len(all_facts)} total facts in this run.</p>'
    body = note + '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Evidence", body, "evidence")


# ---------------------------------------------------------------------------
# Top-level assembler
# ---------------------------------------------------------------------------

_CSS = """
body { font-family: system-ui, sans-serif; margin: 0; background: #fafafa; color: #222; }
nav { background: #1a237e; color: #fff; padding: 0.5rem 1rem; position: sticky; top: 0; z-index: 100; display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
nav a { color: #c5cae9; text-decoration: none; font-size: 0.85rem; }
nav a:hover { color: #fff; }
#search-input { padding: 0.3rem 0.6rem; border-radius: 4px; border: none; font-size: 0.9rem; margin-left: auto; }
main { max-width: 1100px; margin: 0 auto; padding: 1rem 1.5rem; }
section { margin-bottom: 2rem; border-bottom: 1px solid #e0e0e0; padding-bottom: 1rem; }
h2 { color: #1a237e; font-size: 1.2rem; margin-bottom: 0.5rem; }
.fact-list { display: flex; flex-direction: column; gap: 0.3rem; }
.fact-row { display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0.6rem; background: #fff; border: 1px solid #e0e0e0; border-radius: 4px; cursor: pointer; flex-wrap: wrap; }
.fact-row:hover { background: #e8eaf6; }
.fact-label { flex: 1; font-size: 0.9rem; word-break: break-all; }
.prov-badge { color: #fff; border-radius: 3px; padding: 1px 6px; font-size: 0.75rem; white-space: nowrap; }
.conf-bar { width: 60px; height: 6px; background: #e0e0e0; border-radius: 3px; overflow: hidden; flex-shrink: 0; }
.conf-fill { height: 100%; background: #42a5f5; }
.not-analyzed { color: #888; font-style: italic; }
.mermaid-hint { color: #aaa; font-size: 0.8rem; }
pre.mermaid { background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; padding: 1rem; font-size: 0.8rem; overflow-x: auto; }
#evidence-panel { display: none; position: fixed; bottom: 0; left: 0; right: 0; background: #263238; color: #eceff1; padding: 1rem; max-height: 40vh; overflow-y: auto; z-index: 200; font-size: 0.85rem; }
#evidence-panel pre { margin: 0; white-space: pre-wrap; }
#evidence-close { float: right; cursor: pointer; font-size: 1.2rem; }
.hidden { display: none !important; }
"""

_JS = """
function showEvidence(el) {
  const raw = el.getAttribute('data-evidence');
  if (!raw) return;
  const panel = document.getElementById('evidence-panel');
  document.getElementById('evidence-content').textContent = JSON.stringify(JSON.parse(raw), null, 2);
  panel.style.display = 'block';
}
document.getElementById('evidence-close').addEventListener('click', function() {
  document.getElementById('evidence-panel').style.display = 'none';
});
document.getElementById('search-input').addEventListener('input', function() {
  const q = this.value.toLowerCase();
  document.querySelectorAll('.fact-row').forEach(function(row) {
    row.classList.toggle('hidden', q && !row.textContent.toLowerCase().includes(q));
  });
});
"""


def generate_report(store: FactStore, run_id: str, output_dir: Path | None = None) -> Path:
    """Generate a self-contained HTML report from the FactStore for the given run_id."""
    out_dir = output_dir or Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"atlas-report-{run_id}.html"

    timestamp = datetime.now(tz=UTC).isoformat()

    repo_facts = list(store.query_facts(type="git_repository_detected", run_id=run_id))
    repo_path = repo_facts[0].subject.id if repo_facts else "unknown"

    nav_items = [
        ("executive-summary", "Executive Summary"),
        ("system-map", "System Map"),
        ("architecture", "Architecture"),
        ("code-map", "Code Map"),
        ("hotspots", "Hotspots"),
        ("domain-understanding", "Domain"),
        ("runtime", "Runtime"),
        ("infrastructure", "Infrastructure"),
        ("ci-cd", "CI/CD"),
        ("data-architecture", "Data"),
        ("observability", "Observability"),
        ("tests", "Tests"),
        ("git-evolution", "Git Evolution"),
        ("risks-anomalies", "Risks"),
        ("onboarding-path", "Onboarding"),
        ("glossary", "Glossary"),
        ("evidence", "Evidence"),
    ]
    nav_links = "".join(f'<a href="#{sid}">{_esc(label)}</a>' for sid, label in nav_items)

    sections = "\n".join([
        _render_executive_summary(store, run_id),
        _render_system_map(store, run_id),
        _render_architecture(store, run_id),
        _render_code_map(store, run_id),
        _render_hotspots(store, run_id),
        _render_domain(store, run_id),
        _not_analyzed_section("Runtime", "runtime"),
        _not_analyzed_section("Infrastructure", "infrastructure"),
        _not_analyzed_section("CI/CD", "ci-cd"),
        _not_analyzed_section("Data Architecture", "data-architecture"),
        _not_analyzed_section("Observability", "observability"),
        _not_analyzed_section("Tests", "tests"),
        _render_git_evolution(store, run_id),
        _render_risks(store, run_id),
        _not_analyzed_section("Onboarding Path", "onboarding-path"),
        _render_glossary(store, run_id),
        _render_evidence(store, run_id),
    ])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="atlas-run-id" content="{_esc(run_id)}">
<meta name="atlas-generated-at" content="{_esc(timestamp)}">
<meta name="atlas-repository" content="{_esc(repo_path)}">
<title>Atlas Report — {_esc(run_id)}</title>
<style>{_CSS}</style>
</head>
<body>
<nav>
<strong style="color:#fff;margin-right:0.5rem">Atlas</strong>
{nav_links}
<input id="search-input" type="search" placeholder="Search…">
</nav>
<main>{sections}</main>
<div id="evidence-panel">
<span id="evidence-close">✕</span>
<strong>Evidence</strong>
<pre id="evidence-content"></pre>
</div>
<script>{_JS}</script>
</body>
</html>"""

    out_path.write_text(html, encoding="utf-8")
    return out_path

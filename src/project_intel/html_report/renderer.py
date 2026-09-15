"""HTML report renderer — produces a single self-contained offline HTML file."""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.resources
import json
import math
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


def _gap_message_html(msg: str) -> str:
    return f'<p class="not-analyzed">{_esc(msg)}</p>'


def _node_id(path: str) -> str:
    """Stable, collision-free Mermaid node id derived from a full file path."""
    return "n_" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:10]


# ---------------------------------------------------------------------------
# Cross-run fallback (part E) and stage-gap messages (part F)
# ---------------------------------------------------------------------------


def _query_fallback(
    store: FactStore, type_: str, run_id: str
) -> tuple[list[Fact], tuple[str, datetime] | None]:
    """Query facts of `type_` for `run_id`; if empty, fall back to the most recent
    other run that has any. Returns (facts, fallback_info) where fallback_info is
    (run_id, created_at) of the run the facts came from, or None if no fallback used."""
    facts = list(store.query_facts(type=type_, run_id=run_id))
    if facts:
        return facts, None
    all_facts = list(store.query_facts(type=type_))
    if not all_facts:
        return [], None
    by_run: dict[str, list[Fact]] = {}
    for f in all_facts:
        by_run.setdefault(f.run_id, []).append(f)
    best_run = max(by_run, key=lambda rid: max(f.created_at for f in by_run[rid]))
    chosen = by_run[best_run]
    latest = max(f.created_at for f in chosen)
    return chosen, (best_run, latest)


def _fallback_note(section_desc: str, fallback: tuple[str, datetime], noun: str) -> str:
    run_id, ts = fallback
    return (
        f"No {section_desc} for this run. Showing results from a previous analysis "
        f"(run `{run_id[:8]}`, {ts.strftime('%Y-%m-%d %H:%M')}) — {noun}."
    )


def _gap_message(store: FactStore, run_id: str, stage: str, section: str) -> str:
    """Part F: distinct not-analyzed states, based on stage_run_result facts."""
    facts, _fallback = _query_fallback(store, "stage_run_result", run_id)
    stage_facts = [f for f in facts if (f.value or {}).get("stage") == stage]
    if not stage_facts:
        return _not_analyzed(section)

    v = stage_facts[-1].value or {}
    status = v.get("status")
    detail = str(v.get("detail") or "")
    facts_produced = v.get("facts_produced", 0)

    if status == "skipped" and "llm_disabled" in detail:
        return _gap_message_html("LLM analysis was disabled for this run.")
    if status in ("skipped", "failed"):
        return _gap_message_html(f"Atlas attempted this analysis but it failed: {detail}.")
    if status == "ok" and facts_produced == 0:
        return _gap_message_html(
            f"Atlas analyzed this repository for {section} and found nothing to report."
        )
    return _not_analyzed(section)


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _narrative(text: str) -> str:
    return f'<p class="section-narrative">{_esc(text)}</p>\n'


def _join_list(items: list[str], limit: int = 5) -> str:
    """Join up to `limit` items; append '…' if truncated."""
    shown = items[:limit]
    suffix = ", …" if len(items) > limit else ""
    return ", ".join(shown) + suffix


# ---------------------------------------------------------------------------
# Mermaid inline script
# ---------------------------------------------------------------------------

def _mermaid_script() -> str:
    pkg = importlib.resources.files("project_intel.html_report")
    js = (pkg / "_mermaid.min.js").read_text(encoding="utf-8")
    return (
        f'<script>{js}</script>\n'
        '<script>mermaid.initialize({startOnLoad:true});mermaid.run();</script>'
    )


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
    langs, langs_fb = _query_fallback(store, "language_detected", run_id)
    techs, techs_fb = _query_fallback(store, "technology_detected", run_id)
    repos, repos_fb = _query_fallback(store, "git_repository_detected", run_id)

    if not langs and not techs and not repos:
        return _section(
            "Executive Summary", _gap_message(store, run_id, "discovery", "discovery"), "executive-summary"
        )

    rows = []
    for f in repos:
        rows.append(_fact_row(f"Repository: {f.subject.id}", f))
    for f in langs:
        name = (f.value or {}).get("language", f.subject.id)
        rows.append(_fact_row(f"Language: {name}", f))
    for f in techs:
        name = (f.value or {}).get("name", f.subject.id)
        rows.append(_fact_row(f"Technology: {name}", f))

    # Narrative
    lang_names = [
        (f.value or {}).get("language", f.subject.id) for f in langs
    ]
    tech_names = [
        (f.value or {}).get("name", f.subject.id) for f in techs
    ]
    parts: list[str] = []
    if lang_names:
        n = len(lang_names)
        parts.append(
            f"Atlas analyzed {n} language{'s' if n != 1 else ''}: {_join_list(lang_names)}."
        )
    if langs_fb:
        parts.append(_fallback_note("language data", langs_fb, f"{len(lang_names)} language(s) found"))
    if tech_names:
        n = len(tech_names)
        parts.append(
            f"Detected {n} {'technologies' if n != 1 else 'technology'}: {_join_list(tech_names)}."
        )
    if techs_fb:
        parts.append(_fallback_note("technology data", techs_fb, f"{len(tech_names)} technology(ies) found"))
    if repos_fb:
        parts.append(_fallback_note("repository data", repos_fb, f"{len(repos)} repository(ies) found"))
    prose = _narrative(" ".join(parts)) if parts else ""

    body = prose + '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Executive Summary", body, "executive-summary")


def _centrality_combined(f: Fact) -> float:
    v = f.value or {}
    return float(v.get("in_degree", 0)) + float(v.get("out_degree", 0))


def _render_system_map(store: FactStore, run_id: str) -> str:
    centrality, centrality_fb = _query_fallback(store, "centrality", run_id)
    if not centrality:
        return _section("System Map", _gap_message(store, run_id, "code_graph", "code-graph"), "system-map")

    top = sorted(centrality, key=_centrality_combined, reverse=True)[:20]
    diagram_nodes = top[:10]
    node_ids = {f.subject.id: _node_id(f.subject.id) for f in diagram_nodes}
    node_lines = [
        f"  {node_ids[f.subject.id]}[{_esc(f.subject.id.split('/')[-1])}]" for f in diagram_nodes
    ]

    # Real edges: imports/calls relations between two nodes already in the diagram.
    edge_run_id = centrality_fb[0] if centrality_fb else run_id
    edge_lines: list[str] = []
    seen_edges: set[tuple[str, str]] = set()
    for rel_type in ("imports", "calls"):
        for f in store.query_facts(type=rel_type, run_id=edge_run_id):
            src = f.subject.id
            tgt = f.object.id if f.object else None
            if src not in node_ids or tgt not in node_ids:
                continue
            key = (node_ids[src], node_ids[tgt])
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edge_lines.append(f"  {node_ids[src]} --> {node_ids[tgt]}")

    mermaid = "graph LR\n" + "\n".join(node_lines + edge_lines)
    rows = [_fact_row(f.subject.id, f) for f in top]

    top_file = top[0].subject.id if top else None
    parts = [
        f"{len(centrality)} file{'s' if len(centrality) != 1 else ''} ranked by centrality."
        + (f" Top file: {top_file}." if top_file else "")
    ]
    if centrality_fb:
        parts.append(_fallback_note("code-graph data", centrality_fb, f"{len(centrality)} file(s) found"))
    prose = _narrative(" ".join(parts))

    body = (
        prose
        + f'<pre class="mermaid">{mermaid}</pre>'
        + f'<div class="fact-list">{"".join(rows)}</div>'
    )
    return _section("System Map", body, "system-map")


def _render_architecture(store: FactStore, run_id: str) -> str:
    facts, fb = _query_fallback(store, "architecture_hypothesis", run_id)
    if not facts:
        return _section("Architecture", _gap_message(store, run_id, "architecture", "architecture"), "architecture")

    rows = []
    prose_parts: list[str] = []
    for f in facts:
        label = (f.value or {}).get("pattern", f.subject.id)
        rows.append(_fact_row(str(label), f))
        desc = (f.value or {}).get("pattern_description", "")
        if desc:
            prose_parts.append(str(desc))

    if not prose_parts:
        # Fallback: pattern + confidence
        for f in facts:
            pattern = (f.value or {}).get("pattern", f.subject.id)
            prose_parts.append(
                f"Atlas identified the {pattern} pattern with {f.confidence:.0%} confidence."
            )

    if fb:
        prose_parts.append(_fallback_note("architecture data", fb, f"{len(facts)} hypotheses found"))

    prose = _narrative(" ".join(prose_parts)) if prose_parts else ""
    body = prose + '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Architecture", body, "architecture")


def _symbol_label(f: Fact) -> str:
    v = f.value or {}
    name = v.get("name")
    kind = v.get("kind")
    file_ = v.get("file")
    if name and kind and file_:
        return f"{name} ({kind}) — {file_}"
    return f.subject.id


_COMMUNITY_TOP_N = 20
_BUBBLE_MIN_R = 8.0
_BUBBLE_MAX_R = 50.0
_EDGE_MIN_WIDTH = 1.0
_EDGE_MAX_WIDTH = 8.0
_HUE_LIGHT = (227, 242, 253)  # light blue
_HUE_DARK = (13, 71, 161)  # dark blue


def _evidence_json_multi(facts: list[Fact]) -> str:
    """Same shape as `_evidence_json`, concatenated across several facts (a community
    isn't a single Fact, so its evidence is the union of its member facts' evidence)."""
    evs = []
    for fact in facts:
        for ev in fact.evidence:
            d: dict[str, Any] = {
                "kind": ev.kind,
                "source_analyzer": ev.source_analyzer,
                "retrieved_at": ev.retrieved_at.isoformat(),
            }
            d.update(dataclasses.asdict(ev.ref))
            evs.append(d)
    return json.dumps(evs, ensure_ascii=False)


def _lerp_color(t: float, low: tuple[int, int, int], high: tuple[int, int, int]) -> str:
    t = max(0.0, min(1.0, t))
    r = round(low[0] + (high[0] - low[0]) * t)
    g = round(low[1] + (high[1] - low[1]) * t)
    b = round(low[2] + (high[2] - low[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _render_community_graph(
    communities: list[Fact],
    centrality: list[Fact],
    edges_source: list[Fact],
) -> tuple[str, int]:
    """Build the inline SVG community bubble graph. Returns (svg_html, omitted_count)."""
    by_id: dict[Any, list[Fact]] = {}
    for f in communities:
        cid = (f.value or {}).get("community_id", f.subject.id)
        by_id.setdefault(cid, []).append(f)

    centrality_by_file: dict[str, float] = {}
    centrality_fact_by_file: dict[str, Fact] = {}
    for f in centrality:
        centrality_by_file[f.subject.id] = _centrality_combined(f)
        centrality_fact_by_file[f.subject.id] = f

    file_to_community: dict[str, Any] = {}
    for cid, facts in by_id.items():
        for f in facts:
            file_to_community[f.subject.id] = cid

    ranked = sorted(by_id.items(), key=lambda kv: (-len(kv[1]), str(kv[0])))
    selected = ranked[:_COMMUNITY_TOP_N]
    omitted = len(ranked) - len(selected)
    selected_ids = {cid for cid, _ in selected}

    sizes = {cid: len(facts) for cid, facts in selected}
    importances = {
        cid: sum(centrality_by_file.get(p, 0.0) for p in (f.subject.id for f in facts))
        for cid, facts in selected
    }

    # Inter-community edge weights (directed, then merged into one undirected weight per
    # pair for rendering — same "both endpoints must be selected" rule as System Map).
    edge_weights: dict[tuple[Any, Any], int] = {}
    for f in edges_source:
        src = f.subject.id
        tgt = f.object.id if f.object else None
        if tgt is None:
            continue
        ca = file_to_community.get(src)
        cb = file_to_community.get(tgt)
        if ca is None or cb is None or ca == cb:
            continue
        if ca not in selected_ids or cb not in selected_ids:
            continue
        key = tuple(sorted((ca, cb), key=str))
        edge_weights[key] = edge_weights.get(key, 0) + 1

    # Deterministic layout order: by community_id, not by size/rank.
    layout_order = sorted(selected_ids, key=str)
    n = len(layout_order)
    cx, cy, layout_r = 300, 300, 220
    positions: dict[Any, tuple[float, float]] = {}
    for i, cid in enumerate(layout_order):
        angle = 2 * math.pi * i / n if n else 0.0
        positions[cid] = (cx + layout_r * math.cos(angle), cy + layout_r * math.sin(angle))

    max_size = max(sizes.values()) if sizes else 1
    radius_scale = _BUBBLE_MAX_R / (max_size**0.5) if max_size else 0.0

    imp_values = list(importances.values())
    min_imp = min(imp_values) if imp_values else 0.0
    max_imp = max(imp_values) if imp_values else 0.0

    max_weight = max(edge_weights.values()) if edge_weights else 0

    edge_svg: list[str] = []
    for (ca, cb), weight in edge_weights.items():
        x1, y1 = positions[ca]
        x2, y2 = positions[cb]
        width = (
            _EDGE_MIN_WIDTH + (_EDGE_MAX_WIDTH - _EDGE_MIN_WIDTH) * (weight / max_weight)
            if max_weight
            else _EDGE_MIN_WIDTH
        )
        edge_svg.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#9fa8da" stroke-width="{width:.1f}" />'
        )

    bubble_svg: list[str] = []
    for cid, facts in selected:
        x, y = positions[cid]
        size = sizes[cid]
        importance = importances[cid]
        r = max(_BUBBLE_MIN_R, radius_scale * (size**0.5))
        t = (importance - min_imp) / (max_imp - min_imp) if max_imp > min_imp else 0.5
        fill = _lerp_color(t, _HUE_LIGHT, _HUE_DARK)

        member_files = [f.subject.id for f in facts]
        evidence_facts = list(facts) + [
            centrality_fact_by_file[p] for p in member_files if p in centrality_fact_by_file
        ]
        ev = _evidence_json_multi(evidence_facts)
        label = _esc(f"C{cid} — {size} files, importance {round(importance)}")
        bubble_svg.append(
            f'<g class="community-bubble" data-evidence=\'{ev}\' onclick="showEvidence(this)" '
            f'style="cursor:pointer">'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" stroke="#1a237e" '
            f'stroke-width="1" />'
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" dominant-baseline="middle" '
            f'font-size="9" fill="#000">{label}</text>'
            f'</g>'
        )

    svg = (
        '<svg class="community-graph" viewBox="0 0 600 600" xmlns="http://www.w3.org/2000/svg">'
        + "".join(edge_svg)
        + "".join(bubble_svg)
        + "</svg>"
    )
    return svg, omitted


def _render_code_map(store: FactStore, run_id: str) -> str:
    symbols, symbols_fb = _query_fallback(store, "symbol_defined", run_id)
    communities, communities_fb = _query_fallback(store, "community", run_id)
    if not symbols and not communities:
        return _section("Code Map", _gap_message(store, run_id, "code_graph", "code-graph"), "code-map")

    rows = [_fact_row(_symbol_label(f), f) for f in symbols[:30]]

    graph_html = ""
    parts: list[str] = []
    if communities:
        centrality, _centrality_fb = _query_fallback(store, "centrality", run_id)
        edges_run_id = communities_fb[0] if communities_fb else run_id
        edges_source: list[Fact] = []
        for rel_type in ("imports", "calls"):
            edges_source.extend(store.query_facts(type=rel_type, run_id=edges_run_id))

        graph_html, omitted = _render_community_graph(communities, centrality, edges_source)

        n_communities = len({(f.value or {}).get("community_id", f.subject.id) for f in communities})
        shown = min(n_communities, _COMMUNITY_TOP_N)
        parts.append(
            f"{n_communities} community cluster{'s' if n_communities != 1 else ''} detected; "
            f"{shown} largest shown"
            + (f", {omitted} smaller communities not pictured." if omitted else ".")
        )
        if communities_fb:
            parts.append(
                _fallback_note("community data", communities_fb, f"{n_communities} community(ies) found")
            )

    n_sym = len(symbols)
    if n_sym:
        parts.append(f"{n_sym} symbol{'s' if n_sym != 1 else ''} defined.")
    if symbols_fb:
        parts.append(_fallback_note("symbol data", symbols_fb, f"{n_sym} symbol(s) found"))
    prose = _narrative(" ".join(parts)) if parts else ""

    body = prose + graph_html + '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Code Map", body, "code-map")


def _render_hotspots(store: FactStore, run_id: str) -> str:
    facts, fb = _query_fallback(store, "hotspot_score", run_id)
    if not facts:
        return _section("Hotspots", _gap_message(store, run_id, "hotspots", "hotspots"), "hotspots")

    top = sorted(facts, key=lambda f: float((f.value or {}).get("combined", 0)), reverse=True)[:30]
    rows = [
        _fact_row(
            f"{f.subject.id} (score: {float((f.value or {}).get('combined', 0)):.2f})",
            f,
        )
        for f in top
    ]

    top_file = top[0].subject.id
    top_score = float((top[0].value or {}).get("combined", 0))
    n = len(facts)
    parts = [
        (
            f"The {n} highest-scoring file{'s' if n != 1 else ''} are ranked by hotspot score."
            f" Top hotspot: {top_file} ({top_score:.2f})."
        ),
    ]
    if fb:
        parts.append(_fallback_note("hotspot data", fb, f"{n} file(s) found"))
    prose = _narrative(" ".join(parts))

    body = prose + '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Hotspots", body, "hotspots")


def _render_domain(store: FactStore, run_id: str) -> str:
    concepts, concepts_fb = _query_fallback(store, "business_concept", run_id)
    workflows, workflows_fb = _query_fallback(store, "business_workflow", run_id)
    if not concepts and not workflows:
        return _section(
            "Domain Understanding", _gap_message(store, run_id, "domain", "domain"), "domain-understanding"
        )

    rows = []
    for f in concepts:
        name = (f.value or {}).get("name", f.subject.id)
        rows.append(_fact_row(f"Concept: {name}", f))
    for f in workflows:
        name = (f.value or {}).get("name", f.subject.id)
        rows.append(_fact_row(f"Workflow: {name}", f))

    # Narrative: first 3 concept descriptions
    concept_descs: list[str] = []
    for f in concepts[:3]:
        name = (f.value or {}).get("name", f.subject.id)
        desc = (f.value or {}).get("description", "")
        concept_descs.append(f"{name}" + (f" ({desc})" if desc else ""))
    prose_parts: list[str] = []
    if concept_descs:
        prose_parts.append(f"Key concepts: {', '.join(concept_descs)}.")
    if workflows:
        wf_names = [(f.value or {}).get("name", f.subject.id) for f in workflows[:3]]
        prose_parts.append(f"Workflows: {', '.join(wf_names)}.")
    if concepts_fb:
        prose_parts.append(_fallback_note("domain concept data", concepts_fb, f"{len(concepts)} concept(s) found"))
    if workflows_fb:
        prose_parts.append(_fallback_note("workflow data", workflows_fb, f"{len(workflows)} workflow(s) found"))
    prose = _narrative(" ".join(prose_parts)) if prose_parts else ""

    body = prose + '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Domain Understanding", body, "domain-understanding")


def _not_analyzed_section(title: str, section_id: str) -> str:
    return _section(title, _not_analyzed(section_id.replace("-", "_")), section_id)


def _render_git_evolution(store: FactStore, run_id: str) -> str:
    churn, churn_fb = _query_fallback(store, "git_churn", run_id)
    cochange, cochange_fb = _query_fallback(store, "git_co_change", run_id)
    if not churn and not cochange:
        return _section("Git Evolution", _gap_message(store, run_id, "git", "git"), "git-evolution")

    top_churn = sorted(churn, key=lambda f: int((f.value or {}).get("commits", 0)), reverse=True)[:20]
    rows = [_fact_row(f"{f.subject.id} ({(f.value or {}).get('commits', '?')} commits)", f) for f in top_churn]
    for f in cochange[:10]:
        co = (f.value or {}).get("co_occurrences")
        label = f"Co-change: {f.subject.id} ↔ {f.object.id if f.object else '?'}"
        if co is not None:
            label += f" ({co} co-occurrences)"
        rows.append(_fact_row(label, f))

    parts: list[str] = []
    if churn:
        parts.append(f"{len(churn)} file{'s' if len(churn) != 1 else ''} tracked in git history.")
    if top_churn:
        top_file = top_churn[0].subject.id
        top_commits = (top_churn[0].value or {}).get("commits", "?")
        parts.append(f"Highest-churn file: {top_file} ({top_commits} commits).")
    if churn_fb:
        parts.append(_fallback_note("git churn data", churn_fb, f"{len(churn)} file(s) found"))
    if cochange_fb:
        parts.append(_fallback_note("git co-change data", cochange_fb, f"{len(cochange)} pair(s) found"))
    prose = _narrative(" ".join(parts)) if parts else ""

    body = prose + '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Git Evolution", body, "git-evolution")


def _render_risks(store: FactStore, run_id: str) -> str:
    cycles, fb = _query_fallback(store, "dependency_cycle", run_id)
    if not cycles:
        return _section("Risks / Anomalies", _gap_message(store, run_id, "code_graph", "dependency_cycle"), "risks-anomalies")

    rows = []
    for f in cycles:
        members = (f.value or {}).get("cycle_members")
        if members:
            label = "Cycle: " + " → ".join(str(m) for m in members)
        else:
            label = f"Dependency cycle: {f.subject.id}"
        rows.append(_fact_row(label, f))
    n = len(cycles)
    parts = [f"{n} dependency cycle{'s' if n != 1 else ''} detected."]
    if fb:
        parts.append(_fallback_note("dependency cycle data", fb, f"{n} cycle(s) found"))
    prose = _narrative(" ".join(parts))

    body = prose + '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Risks / Anomalies", body, "risks-anomalies")


def _ensure_period(s: str) -> str:
    s = s.rstrip()
    return s if s.endswith((".", "!", "?")) else s + "."


def _render_onboarding(store: FactStore, run_id: str) -> str:
    paths, fb = _query_fallback(store, "onboarding_path", run_id)
    if not paths:
        return _section(
            "Onboarding Path", _gap_message(store, run_id, "onboarding", "onboarding"), "onboarding-path"
        )

    rows = [_fact_row(f.subject.id, f) for f in paths]
    prose_parts: list[str] = []
    for f in paths[:1]:
        v = f.value or {}
        rw_desc = v.get("recommended_workflow", {}).get("description", "")
        if rw_desc:
            prose_parts.append(_ensure_period(str(rw_desc)))
        tb = v.get("time_boxed_understanding", {})
        thirty = tb.get("thirty_minutes", "")
        two_hrs = tb.get("two_hours", "")
        if thirty:
            prose_parts.append(_ensure_period(f"First 30 minutes: {thirty}"))
        if two_hrs:
            prose_parts.append(_ensure_period(f"First 2 hours: {two_hrs}"))
    if fb:
        prose_parts.append(_fallback_note("onboarding data", fb, f"{len(paths)} path(s) found"))
    prose = _narrative(" ".join(prose_parts)) if prose_parts else ""

    body = prose + '<div class="fact-list">' + "".join(rows) + "</div>"
    return _section("Onboarding Path", body, "onboarding-path")


def _render_glossary(store: FactStore, run_id: str) -> str:
    terms, fb = _query_fallback(store, "glossary_term", run_id)
    if not terms:
        return _section("Glossary", _gap_message(store, run_id, "domain", "glossary"), "glossary")

    rows = []
    for f in terms:
        term = (f.value or {}).get("term", f.subject.id)
        definition = (f.value or {}).get("definition", "")
        rows.append(_fact_row(f"{term}: {definition}", f))
    prose = _narrative(_fallback_note("glossary data", fb, f"{len(terms)} term(s) found")) if fb else ""
    body = prose + '<div class="fact-list">' + "".join(rows) + "</div>"
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
.section-narrative { color: #444; font-size: 0.95rem; margin: 0 0 0.75rem 0; line-height: 1.5; }
.fact-list { display: flex; flex-direction: column; gap: 0.3rem; }
.fact-row { display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem 0.6rem; background: #fff; border: 1px solid #e0e0e0; border-radius: 4px; cursor: pointer; flex-wrap: wrap; }
.fact-row:hover { background: #e8eaf6; }
.fact-label { flex: 1; font-size: 0.9rem; word-break: break-all; }
.prov-badge { color: #fff; border-radius: 3px; padding: 1px 6px; font-size: 0.75rem; white-space: nowrap; }
.conf-bar { width: 60px; height: 6px; background: #e0e0e0; border-radius: 3px; overflow: hidden; flex-shrink: 0; }
.conf-fill { height: 100%; background: #42a5f5; }
.not-analyzed { color: #888; font-style: italic; }
pre.mermaid { background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; padding: 1rem; font-size: 0.8rem; overflow-x: auto; }
svg.community-graph { width: 100%; max-width: 600px; height: auto; background: #f5f5f5; border: 1px solid #ddd; border-radius: 4px; }
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
        _render_onboarding(store, run_id),
        _render_glossary(store, run_id),
        _render_evidence(store, run_id),
    ])

    mermaid_script = _mermaid_script()

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
{mermaid_script}
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

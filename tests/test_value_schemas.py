"""Tests for Feature 01b — typed fact value schemas.

Reproduces this session's four historical silent-fallback bugs as TypeError
cases (the exact wrong keys a consumer once used), proving the typed
accessors make that mistake impossible instead of silently returning a
fallback.
"""

from __future__ import annotations

import pytest

from project_intel.facts.value_schemas import (
    CentralityValue,
    HotspotScoreValue,
    TechnologyDetectedValue,
)

# ---------------------------------------------------------------------------
# Historical bug #1: html_report/renderer.py used .get("technology", ...)
# for technology_detected, whose real key is "name".
# ---------------------------------------------------------------------------


def test_technology_detected_wrong_key_raises():
    wrong = {"category": "build", "technology": "maven"}  # "technology" instead of "name"
    with pytest.raises(TypeError):
        TechnologyDetectedValue(**wrong)


# ---------------------------------------------------------------------------
# Historical bug #2: html_report/renderer.py used .get("score", ...)
# for hotspot_score, whose real key is "combined".
# ---------------------------------------------------------------------------


def test_hotspot_score_wrong_key_score_raises():
    wrong = {"score": 0.5, "components_available": "3/4", "components": {}}
    with pytest.raises(TypeError):
        HotspotScoreValue(**wrong)


# ---------------------------------------------------------------------------
# Historical bug #3: mcp_server/queries.py used .get("combined_score", ...)
# for the same hotspot_score fact — a different wrong guess, same real key.
# ---------------------------------------------------------------------------


def test_hotspot_score_wrong_key_combined_score_raises():
    wrong = {"combined_score": 0.5, "components_available": "3/4", "components": {}}
    with pytest.raises(TypeError):
        HotspotScoreValue(**wrong)


# ---------------------------------------------------------------------------
# Historical bug #4: a sort routine keyed centrality on "score", whose real
# keys are "in_degree"/"out_degree".
# ---------------------------------------------------------------------------


def test_centrality_wrong_key_raises():
    wrong = {"score": 0.7}
    with pytest.raises(TypeError):
        CentralityValue(**wrong)

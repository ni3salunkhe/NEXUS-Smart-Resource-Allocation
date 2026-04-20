"""
NEXUS Phase 0.5 — Household Registry Validation Tests
Tests: identity resolution logic, schema validation, consent, merge, history
"""
import pytest
import math
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from datetime import datetime, timezone

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.registry.identity_resolution import (
    _jaccard, _vulnerability_cosine, _family_size_score,
    _distance_score, _stage3_fuzzy, _stage4_composite,
    AUTO_LINK_THRESHOLD, REVIEW_THRESHOLD,
    W_GEO, W_LANDMARK, W_VULN, W_TEXT, W_SIZE,
)
from services.registry.schemas import (
    HouseholdCreate, HouseholdUpdate, MemberCreate, LocationInput,
    ConsentCreate, ConsentType, ConsentMethod, MergeRequest,
    IdentityResolutionRequest, SearchRequest,
    DwellingType, EconomicTier, AgeBracket, MemberRole,
)


# ── Jaccard similarity ────────────────────────────────────────
class TestJaccard:
    def test_identical_lists(self):
        assert _jaccard(["a", "b", "c"], ["a", "b", "c"]) == 1.0

    def test_no_overlap(self):
        assert _jaccard(["a", "b"], ["c", "d"]) == 0.0

    def test_partial_overlap(self):
        score = _jaccard(["a", "b", "c"], ["b", "c", "d"])
        assert abs(score - 0.5) < 0.01  # intersection=2, union=4

    def test_empty_lists(self):
        assert _jaccard([], []) == 0.0

    def test_one_empty(self):
        assert _jaccard(["a", "b"], []) == 0.0

    def test_landmark_match_same_tags(self):
        tags = ["near dargah", "red door", "main road"]
        assert _jaccard(tags, tags) == 1.0

    def test_landmark_partial(self):
        a = ["near dargah", "red door"]
        b = ["near dargah", "blue gate"]
        score = _jaccard(a, b)
        assert 0 < score < 1.0


# ── Vulnerability cosine ──────────────────────────────────────
class TestVulnerabilityCosine:
    def test_identical_flags(self):
        flags = {"has_child": True, "has_elderly": False, "has_disabled": True}
        score = _vulnerability_cosine(flags, flags)
        assert abs(score - 1.0) < 0.001

    def test_no_overlap(self):
        a = {"has_child": True,  "has_elderly": False}
        b = {"has_child": False, "has_elderly": True}
        score = _vulnerability_cosine(a, b)
        assert score == 0.0

    def test_empty_flags(self):
        assert _vulnerability_cosine({}, {}) == 0.0

    def test_partial_overlap(self):
        a = {"has_child": True,  "has_elderly": True,  "has_disabled": False}
        b = {"has_child": True,  "has_elderly": False, "has_disabled": False}
        score = _vulnerability_cosine(a, b)
        assert 0 < score < 1.0

    def test_one_empty(self):
        a = {"has_child": True}
        assert _vulnerability_cosine(a, {}) == 0.0


# ── Family size scoring ───────────────────────────────────────
class TestFamilySize:
    @pytest.mark.parametrize("req,hh,expected_min,expected_max", [
        (4, 4, 0.99, 1.01),
        (4, 5, 0.79, 0.81),
        (4, 6, 0.49, 0.51),
        (4, 8, 0.09, 0.11),
        (None, 4, 0.49, 0.51),  # neutral when unknown
    ])
    def test_family_size_ranges(self, req, hh, expected_min, expected_max):
        score = _family_size_score(req, hh)
        assert expected_min <= score <= expected_max


# ── Distance scoring ──────────────────────────────────────────
class TestDistanceScore:
    def test_zero_distance(self):
        assert _distance_score(0) == 1.0

    def test_50m(self):
        assert abs(_distance_score(50) - 0.5) < 0.01

    def test_100m(self):
        assert _distance_score(100) == 0.0

    def test_over_100m(self):
        assert _distance_score(150) == 0.0

    def test_none(self):
        assert _distance_score(None) == 0.0


# ── Stage 3 fuzzy scoring ─────────────────────────────────────
class TestStage3Fuzzy:
    def _make_req(self, **kwargs):
        defaults = dict(
            landmark_tags=[],
            vulnerability_flags={},
            description_text=None,
            family_size=None,
            dwelling_type=None,
        )
        defaults.update(kwargs)
        return IdentityResolutionRequest(**defaults)

    def _make_candidate(self, **kwargs):
        defaults = dict(
            landmark_tags=[],
            vulnerability_flags={},
            location_description=None,
            total_members=0,
            dwelling_type=None,
        )
        defaults.update(kwargs)
        return defaults

    def test_perfect_landmark_match(self):
        tags = ["near dargah", "red door"]
        req  = self._make_req(landmark_tags=tags)
        cand = self._make_candidate(landmark_tags=tags)
        scores = _stage3_fuzzy(req, cand)
        assert scores["landmark"] == 1.0

    def test_text_similarity(self):
        req  = self._make_req(description_text="family near the pump red door")
        cand = self._make_candidate(location_description="family near the pump")
        scores = _stage3_fuzzy(req, cand)
        assert scores["text"] > 0.5

    def test_dwelling_type_match(self):
        req  = self._make_req(dwelling_type="permanent")
        cand = self._make_candidate(dwelling_type="permanent")
        scores = _stage3_fuzzy(req, cand)
        assert scores["dwelling_type"] == 1.0

    def test_dwelling_type_mismatch(self):
        req  = self._make_req(dwelling_type="permanent")
        cand = self._make_candidate(dwelling_type="temporary")
        scores = _stage3_fuzzy(req, cand)
        assert scores["dwelling_type"] < 0.5


# ── Stage 4 composite ─────────────────────────────────────────
class TestStage4Composite:
    def test_perfect_score(self):
        score = _stage4_composite(
            geo_score=1.0,
            fuzzy_scores={"landmark": 1.0, "vulnerability": 1.0,
                          "text": 1.0, "family_size": 1.0}
        )
        assert abs(score - 1.0) < 0.001

    def test_zero_score(self):
        score = _stage4_composite(
            geo_score=0.0,
            fuzzy_scores={"landmark": 0.0, "vulnerability": 0.0,
                          "text": 0.0, "family_size": 0.0}
        )
        assert score == 0.0

    def test_weights_sum_to_one(self):
        assert abs(W_GEO + W_LANDMARK + W_VULN + W_TEXT + W_SIZE - 1.0) < 0.001

    def test_auto_link_threshold(self):
        # Ensure thresholds are correctly set
        assert AUTO_LINK_THRESHOLD == 0.80
        assert REVIEW_THRESHOLD    == 0.55
        assert AUTO_LINK_THRESHOLD > REVIEW_THRESHOLD

    def test_high_confidence_would_auto_link(self):
        score = _stage4_composite(
            geo_score=0.9,
            fuzzy_scores={"landmark": 0.8, "vulnerability": 0.9,
                          "text": 0.7, "family_size": 1.0}
        )
        assert score >= AUTO_LINK_THRESHOLD

    def test_low_confidence_new_household(self):
        score = _stage4_composite(
            geo_score=0.2,
            fuzzy_scores={"landmark": 0.0, "vulnerability": 0.1,
                          "text": 0.0, "family_size": 0.1}
        )
        assert score < REVIEW_THRESHOLD


# ── Schema validation ─────────────────────────────────────────
class TestSchemas:
    def test_household_create_empty_members(self):
        hh = HouseholdCreate()
        assert hh.members == []

    def test_household_create_with_location(self):
        hh = HouseholdCreate(
            location=LocationInput(
                latitude=19.0760,
                longitude=72.8777,
                confidence=0.9,
                description="Near the water pump",
                landmarks=["water pump", "blue gate"],
            ),
            dwelling_type=DwellingType.temporary,
        )
        assert hh.location.latitude == 19.0760
        assert len(hh.location.landmarks) == 2

    def test_location_requires_both_coords(self):
        with pytest.raises(Exception):
            LocationInput(latitude=19.0760, longitude=None)

    def test_member_create_defaults(self):
        m = MemberCreate()
        assert m.vulnerability_flags == {}
        assert m.is_primary_contact is False

    def test_consent_create(self):
        c = ConsentCreate(
            consent_type=ConsentType.data_collection,
            collection_method=ConsentMethod.digital_app,
            language_used="hi",
        )
        assert c.consent_type == ConsentType.data_collection
        assert "purposes" in c.scope

    def test_merge_request(self):
        src = uuid4()
        tgt = uuid4()
        req = MergeRequest(
            source_household_id=src,
            target_household_id=tgt,
            merge_reason="Duplicate entry confirmed by field coordinator",
        )
        assert req.source_household_id == src

    def test_search_request_defaults(self):
        req = SearchRequest()
        assert req.status == "active"
        assert req.limit == 20
        assert req.radius_m == 500

    def test_identity_resolution_request(self):
        req = IdentityResolutionRequest(
            latitude=19.0760,
            longitude=72.8777,
            landmark_tags=["near dargah", "red door"],
            family_size=5,
            vulnerability_flags={"has_child": True},
        )
        assert len(req.landmark_tags) == 2
        assert req.family_size == 5


# ── History event types ───────────────────────────────────────
class TestHistoryEventTypes:
    def test_all_event_types_defined(self):
        from services.registry.schemas import HHEventType
        required = {
            "need_reported", "need_resolved", "task_dispatched", "task_completed",
            "member_added", "member_removed", "vulnerability_updated",
            "consent_changed", "assistance_received", "location_updated",
            "merged", "linked", "opted_out",
        }
        defined = {e.value for e in HHEventType}
        assert required.issubset(defined)


# ── Consent scope validation ──────────────────────────────────
class TestConsentScope:
    def test_default_scope_structure(self):
        c = ConsentCreate(consent_type=ConsentType.analytics)
        assert "tenants_allowed" in c.scope
        assert "purposes" in c.scope
        assert "data_fields_allowed" in c.scope
        assert isinstance(c.scope["tenants_allowed"], list)

    def test_custom_scope(self):
        c = ConsentCreate(
            consent_type=ConsentType.cross_org_linking,
            scope={
                "tenants_allowed": ["tenant-abc", "tenant-xyz"],
                "purposes": ["cross_org_linking"],
                "data_fields_allowed": ["vulnerability_flags", "ward_id"],
            }
        )
        assert len(c.scope["tenants_allowed"]) == 2
        assert "vulnerability_flags" in c.scope["data_fields_allowed"]


# ── Resolution status logic ───────────────────────────────────
class TestResolutionStatusLogic:
    """
    Verify that composite scores correctly map to resolution statuses.
    Tests the threshold logic without DB.
    """
    @pytest.mark.parametrize("score,expected_status", [
        (0.95, "auto_linked"),
        (0.85, "auto_linked"),
        (0.80, "auto_linked"),   # boundary
        (0.79, "review_required"),
        (0.65, "review_required"),
        (0.55, "review_required"),  # boundary
        (0.54, "new_household"),
        (0.30, "new_household"),
        (0.00, "new_household"),
    ])
    def test_threshold_mapping(self, score, expected_status):
        if score >= AUTO_LINK_THRESHOLD:
            status = "auto_linked"
        elif score >= REVIEW_THRESHOLD:
            status = "review_required"
        else:
            status = "new_household"
        assert status == expected_status


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=os.path.join(os.path.dirname(__file__), "..")
    )
    sys.exit(result.returncode)
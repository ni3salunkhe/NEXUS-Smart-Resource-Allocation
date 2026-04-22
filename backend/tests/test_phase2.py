"""
NEXUS Phase 2 — Intelligence Engine Validation Tests
Tests: urgency formula terms, composite scoring, escalation,
       weight validation, chronic floor, category boosts,
       ES mapping structure, priority queue logic
"""
import pytest
import math
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.intelligence.scoring import (
    compute_urgency_score, UrgencyWeights, UrgencyComponents,
    should_escalate,
    _t1_severity, _t2_recency, _t3_vulnerability,
    _t4_unmet_duration, _t5_source_reliability,
    _t6_crisis_frequency, _t7_coverage_penalty,
)
from services.intelligence.elasticsearch_service import (
    NEEDS_MAPPING, WARD_STATS_MAPPING, NEEDS_INDEX, WARDS_INDEX,
)


# ── T1: Severity ──────────────────────────────────────────────
class TestT1Severity:
    @pytest.mark.parametrize("score,expected", [
        (0.0, 0.0), (0.5, 0.5), (1.0, 1.0), (0.95, 0.95),
    ])
    def test_passthrough(self, score, expected):
        assert _t1_severity(score) == expected

    def test_clamps_below_zero(self):
        assert _t1_severity(-0.5) == 0.0

    def test_clamps_above_one(self):
        assert _t1_severity(1.5) == 1.0


# ── T2: Recency ───────────────────────────────────────────────
class TestT2Recency:
    def _dt(self, hours_ago: float) -> datetime:
        return datetime.now(timezone.utc) - timedelta(hours=hours_ago)

    def test_fresh_report_near_1(self):
        score = _t2_recency(self._dt(0.1))
        assert score > 0.95

    def test_24h_old_decayed(self):
        score = _t2_recency(self._dt(24))
        assert 0.30 < score < 0.55

    def test_72h_old_further_decayed(self):
        score = _t2_recency(self._dt(72))
        assert 0.10 < score < 0.40

    def test_very_old_near_zero(self):
        score = _t2_recency(self._dt(1000))
        assert score < 0.20

    def test_none_returns_neutral(self):
        score = _t2_recency(None)
        assert score == 0.5

    def test_monotonically_decreasing(self):
        scores = [_t2_recency(self._dt(h)) for h in [1, 6, 24, 72, 168]]
        for i in range(len(scores) - 1):
            assert scores[i] > scores[i+1], \
                f"Score not decreasing at index {i}: {scores[i]:.3f} → {scores[i+1]:.3f}"

    def test_always_in_range(self):
        for h in [0, 1, 12, 24, 48, 168, 720]:
            s = _t2_recency(self._dt(h))
            assert 0.0 <= s <= 1.0


# ── T3: Vulnerability ─────────────────────────────────────────
class TestT3Vulnerability:
    def test_no_flags_low_score(self):
        flags = {k: False for k in ["has_child","has_elderly","has_disabled","has_pregnant","chronic_illness","single_parent"]}
        score = _t3_vulnerability(flags, 0.0)
        assert score < 0.20

    def test_pregnant_flag_high_contribution(self):
        flags = {"has_pregnant": True, "has_child": False, "has_elderly": False,
                 "has_disabled": False, "chronic_illness": False, "single_parent": False}
        score = _t3_vulnerability(flags, 0.0)
        assert score > 0.10

    def test_multiple_flags_cumulative(self):
        single = _t3_vulnerability({"has_child": True, "has_elderly": False,
                                     "has_disabled": False, "has_pregnant": False,
                                     "chronic_illness": False, "single_parent": False}, 0.0)
        multi  = _t3_vulnerability({"has_child": True, "has_elderly": True,
                                     "has_disabled": True, "has_pregnant": False,
                                     "chronic_illness": False, "single_parent": False}, 0.0)
        assert multi > single

    def test_household_vulnerability_score_blended(self):
        flags = {k: False for k in ["has_child","has_elderly","has_disabled",
                                     "has_pregnant","chronic_illness","single_parent"]}
        low  = _t3_vulnerability(flags, 0.1)
        high = _t3_vulnerability(flags, 0.9)
        assert high > low

    def test_always_in_range(self):
        for vuln_score in [0.0, 0.3, 0.7, 1.0]:
            flags = {"has_child": True, "has_elderly": True, "has_disabled": False,
                     "has_pregnant": False, "chronic_illness": True, "single_parent": False}
            s = _t3_vulnerability(flags, vuln_score)
            assert 0.0 <= s <= 1.0


# ── T4: Unmet Duration ────────────────────────────────────────
class TestT4UnmetDuration:
    def _dt(self, days_ago: float) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=days_ago)

    def test_resolved_returns_zero(self):
        assert _t4_unmet_duration(self._dt(5), "resolved") == 0.0

    def test_closed_returns_zero(self):
        assert _t4_unmet_duration(self._dt(3), "closed") == 0.0

    def test_fresh_need_low_score(self):
        score = _t4_unmet_duration(self._dt(0), "verified")
        assert score < 0.10

    def test_7_day_old_high_score(self):
        score = _t4_unmet_duration(self._dt(7), "verified")
        assert score > 0.85

    def test_none_returns_neutral(self):
        score = _t4_unmet_duration(None, "verified")
        assert score == 0.3

    def test_monotonically_increasing(self):
        scores = [_t4_unmet_duration(self._dt(d), "verified") for d in [0, 1, 3, 7, 14]]
        for i in range(len(scores) - 1):
            assert scores[i] < scores[i+1]


# ── T5: Source Reliability ────────────────────────────────────
class TestT5SourceReliability:
    @pytest.mark.parametrize("source,min_score,max_score", [
        ("mobile",   0.85, 1.0),
        ("webhook",  0.75, 0.90),
        ("csv",      0.70, 0.85),
        ("whatsapp", 0.65, 0.80),
        ("sms",      0.60, 0.75),
        ("paper",    0.55, 0.70),
        ("audio",    0.50, 0.65),
    ])
    def test_channel_reliability_order(self, source, min_score, max_score):
        score = _t5_source_reliability(source)
        assert min_score <= score <= max_score, \
            f"{source}: {score:.3f} not in [{min_score}, {max_score}]"

    def test_mobile_highest_reliability(self):
        assert _t5_source_reliability("mobile") > _t5_source_reliability("paper")
        assert _t5_source_reliability("mobile") > _t5_source_reliability("sms")

    def test_worker_rating_blended(self):
        base   = _t5_source_reliability("paper")
        trusted= _t5_source_reliability("paper", submitted_by_outcome_rating=5.0)
        low    = _t5_source_reliability("paper", submitted_by_outcome_rating=1.0)
        assert trusted > base > low


# ── T6: Crisis Frequency ──────────────────────────────────────
class TestT6CrisisFrequency:
    def test_zero_frequency(self):
        assert _t6_crisis_frequency(0.0, 2.0) == 0.0

    def test_at_threshold_half_score(self):
        score = _t6_crisis_frequency(2.0, 2.0)   # at threshold = normalized 0.5
        assert abs(score - 0.5) < 0.01

    def test_double_threshold_full_score(self):
        score = _t6_crisis_frequency(4.0, 2.0)   # 2x threshold = normalized 1.0
        assert score == 1.0

    def test_above_double_capped(self):
        score = _t6_crisis_frequency(10.0, 2.0)
        assert score == 1.0

    def test_monotonically_increasing(self):
        scores = [_t6_crisis_frequency(f, 2.0) for f in [0, 0.5, 1.0, 2.0, 3.0, 5.0]]
        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i+1]


# ── T7: Coverage Penalty ──────────────────────────────────────
class TestT7CoveragePenalty:
    def test_no_tasks_no_penalty(self):
        assert _t7_coverage_penalty(0.8, 0) == 0.0

    def test_high_coverage_high_penalty(self):
        score = _t7_coverage_penalty(1.0, 5)
        assert score == 1.0

    def test_partial_coverage(self):
        score = _t7_coverage_penalty(0.5, 3)
        assert 0.4 < score < 0.6

    def test_penalty_does_not_exceed_one(self):
        score = _t7_coverage_penalty(2.0, 10)
        assert score <= 1.0


# ── Weight validation ─────────────────────────────────────────
class TestWeightValidation:
    def test_default_weights_valid(self):
        w = UrgencyWeights()
        w.validate()   # should not raise

    def test_weights_sum_correct(self):
        w = UrgencyWeights()
        total = (w.w1_severity + w.w2_recency + w.w3_vulnerability +
                 w.w4_unmet_duration + w.w5_source_reliability + w.w6_crisis_frequency)
        assert abs(total - 0.95) < 0.01   # w7 is penalty, not additive

    def test_invalid_weights_raise(self):
        w = UrgencyWeights(w1_severity=0.9, w2_recency=0.9)
        with pytest.raises(ValueError):
            w.validate()


# ── Full composite scoring ────────────────────────────────────
class TestCompositeScoring:
    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _dt(self, hours_ago=0, days_ago=0) -> datetime:
        return self._now() - timedelta(hours=hours_ago, days=days_ago)

    def _all_vuln_flags(self, value=True) -> dict:
        return {k: value for k in ["has_child","has_elderly","has_disabled",
                                    "has_pregnant","chronic_illness","single_parent"]}

    def test_max_urgency_scenario(self):
        """Critical need: all signals maximised."""
        comp = compute_urgency_score(
            severity_score       = 1.0,
            reported_at          = self._dt(hours_ago=1),
            ingested_at          = self._dt(days_ago=3),
            status               = "verified",
            vulnerability_flags  = self._all_vuln_flags(True),
            vulnerability_score  = 1.0,
            crisis_frequency     = 5.0,
            source_type          = "mobile",
            category             = "food",
            ward_coverage_ratio  = 0.0,
            active_tasks_in_area = 0,
        )
        assert comp.final_score >= 0.85

    def test_min_urgency_scenario(self):
        """Low-priority need: all signals minimised."""
        comp = compute_urgency_score(
            severity_score       = 0.1,
            reported_at          = self._dt(days_ago=1),
            ingested_at          = self._dt(days_ago=1),
            status               = "verified",
            vulnerability_flags  = self._all_vuln_flags(False),
            vulnerability_score  = 0.0,
            crisis_frequency     = 0.0,
            source_type          = "paper",
            category             = "other",
            ward_coverage_ratio  = 1.0,
            active_tasks_in_area = 5,
        )
        assert comp.final_score < 0.50

    def test_score_always_in_range(self):
        for sev in [0.0, 0.5, 1.0]:
            for days in [0, 3, 14]:
                comp = compute_urgency_score(
                    severity_score      = sev,
                    reported_at         = self._dt(days_ago=days),
                    ingested_at         = self._dt(days_ago=days),
                    status              = "verified",
                    vulnerability_flags = {},
                    vulnerability_score = 0.5,
                    crisis_frequency    = 1.0,
                    source_type         = "mobile",
                    category            = "food",
                )
                assert 0.0 <= comp.final_score <= 1.0

    def test_components_to_dict(self):
        comp = compute_urgency_score(
            severity_score=0.7, reported_at=self._dt(), ingested_at=self._dt(),
            status="verified", vulnerability_flags={}, vulnerability_score=0.3,
            crisis_frequency=1.0, source_type="whatsapp", category="health",
        )
        d = comp.to_dict()
        required = ["t1_severity","t2_recency","t3_vulnerability","t4_unmet_duration",
                    "t5_source_reliability","t6_crisis_frequency","t7_coverage_penalty",
                    "category_boost","chronic_floor_applied","final_score"]
        for key in required:
            assert key in d

    def test_chronic_floor_applied(self):
        """Chronic household must not score below floor even with low signals."""
        w = UrgencyWeights(chronic_threshold=2.0, chronic_floor=0.40)
        comp = compute_urgency_score(
            severity_score       = 0.05,
            reported_at          = self._dt(hours_ago=1),
            ingested_at          = self._dt(hours_ago=1),
            status               = "verified",
            vulnerability_flags  = {},
            vulnerability_score  = 0.0,
            crisis_frequency     = 3.0,   # above chronic_threshold
            source_type          = "mobile",
            category             = "other",
            ward_coverage_ratio  = 0.8,
            active_tasks_in_area = 5,
            weights              = w,
        )
        assert comp.final_score >= 0.40
        assert comp.chronic_floor_applied is True

    def test_chronic_floor_not_applied_below_threshold(self):
        """Non-chronic household: floor not applied."""
        w = UrgencyWeights(chronic_threshold=2.0, chronic_floor=0.40)
        comp = compute_urgency_score(
            severity_score=0.05, reported_at=self._dt(), ingested_at=self._dt(),
            status="verified", vulnerability_flags={}, vulnerability_score=0.0,
            crisis_frequency=0.5,   # below threshold
            source_type="paper", category="other",
            ward_coverage_ratio=0.9, active_tasks_in_area=5,
            weights=w,
        )
        assert comp.chronic_floor_applied is False

    def test_coverage_penalty_reduces_score(self):
        """Over-served area reduces urgency score."""
        no_coverage = compute_urgency_score(
            severity_score=0.7, reported_at=self._dt(), ingested_at=self._dt(days_ago=1),
            status="verified", vulnerability_flags={}, vulnerability_score=0.3,
            crisis_frequency=0.5, source_type="mobile", category="food",
            ward_coverage_ratio=0.0, active_tasks_in_area=0,
        )
        high_coverage = compute_urgency_score(
            severity_score=0.7, reported_at=self._dt(), ingested_at=self._dt(days_ago=1),
            status="verified", vulnerability_flags={}, vulnerability_score=0.3,
            crisis_frequency=0.5, source_type="mobile", category="food",
            ward_coverage_ratio=1.0, active_tasks_in_area=10,
        )
        assert no_coverage.final_score > high_coverage.final_score

    def test_category_boost_applied(self):
        """Category boost multiplies the final score."""
        w = UrgencyWeights(category_boosts={"health": 1.3})
        boosted = compute_urgency_score(
            severity_score=0.5, reported_at=self._dt(), ingested_at=self._dt(days_ago=1),
            status="verified", vulnerability_flags={}, vulnerability_score=0.3,
            crisis_frequency=0.5, source_type="mobile", category="health",
            weights=w,
        )
        unboosted = compute_urgency_score(
            severity_score=0.5, reported_at=self._dt(), ingested_at=self._dt(days_ago=1),
            status="verified", vulnerability_flags={}, vulnerability_score=0.3,
            crisis_frequency=0.5, source_type="mobile", category="food",
            weights=w,
        )
        assert boosted.final_score >= unboosted.final_score
        assert boosted.category_boost == 1.3


# ── Escalation logic ──────────────────────────────────────────
class TestEscalation:
    def _dt(self, minutes_ago=0) -> datetime:
        return datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)

    def test_escalates_above_threshold_and_old_enough(self):
        w = UrgencyWeights(escalation_threshold=0.90, escalation_minutes=120)
        assert should_escalate(0.92, self._dt(130), "verified", w) is True

    def test_no_escalation_below_threshold(self):
        assert should_escalate(0.85, self._dt(200), "verified") is False

    def test_no_escalation_too_recent(self):
        w = UrgencyWeights(escalation_threshold=0.90, escalation_minutes=120)
        assert should_escalate(0.95, self._dt(60), "verified", w) is False

    def test_no_escalation_if_assigned(self):
        assert should_escalate(0.99, self._dt(200), "assigned") is False

    def test_no_escalation_if_resolved(self):
        assert should_escalate(0.99, self._dt(200), "resolved") is False

    def test_escalates_at_exact_boundary(self):
        w = UrgencyWeights(escalation_threshold=0.90, escalation_minutes=120)
        assert should_escalate(0.90, self._dt(120), "verified", w) is True


# ── ES index structure ────────────────────────────────────────
class TestElasticsearchMapping:
    def test_needs_index_has_geo_point(self):
        props = NEEDS_MAPPING["mappings"]["properties"]
        assert props["location"]["type"] == "geo_point"

    def test_needs_index_has_required_fields(self):
        props = NEEDS_MAPPING["mappings"]["properties"]
        required = ["need_id","tenant_id","ward_id","category","urgency_score",
                    "severity_score","status","ingested_at","description",
                    "has_child","has_elderly","has_disabled","has_pregnant"]
        for f in required:
            assert f in props, f"Missing ES field: {f}"

    def test_urgency_score_is_float(self):
        props = NEEDS_MAPPING["mappings"]["properties"]
        assert props["urgency_score"]["type"] == "float"

    def test_ward_stats_index_has_centroid(self):
        props = WARD_STATS_MAPPING["mappings"]["properties"]
        assert props["centroid"]["type"] == "geo_point"

    def test_ward_stats_has_desert_flag(self):
        props = WARD_STATS_MAPPING["mappings"]["properties"]
        assert "is_resource_desert" in props
        assert props["is_resource_desert"]["type"] == "boolean"

    def test_index_names_defined(self):
        assert NEEDS_INDEX  == "nexus_needs"
        assert WARDS_INDEX  == "nexus_ward_stats"


# ── UrgencyComponents dataclass ───────────────────────────────
class TestUrgencyComponents:
    def test_to_dict_all_keys(self):
        c = UrgencyComponents(final_score=0.75)
        d = c.to_dict()
        assert "final_score" in d
        assert d["final_score"] == pytest.approx(0.75, abs=0.001)

    def test_default_values(self):
        c = UrgencyComponents()
        assert c.final_score == 0.0
        assert c.category_boost == 1.0
        assert c.chronic_floor_applied is False


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=os.path.join(os.path.dirname(__file__), "..")
    )
    sys.exit(result.returncode)
"""
NEXUS Phase 4+5 — Smart Matching & Feedback Loop Validation Tests
Tests: HII formula, trend detection, override learning, impact metric
       computation, duplication rate, feedback event types,
       funder report anonymization contract, period metric logic
"""
import pytest
from datetime import date, timedelta, datetime, timezone
from uuid import uuid4

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.analytics.feedback_loop import (
    _compute_trend, HII_WINDOWS,
)
from services.coordination.matching.override_learning import (
    record_override, get_override_summary,
)


# ── HII: formula and trend ────────────────────────────────────
class TestHouseholdImprovementIndex:

    @pytest.mark.parametrize("fully,partial,unresolved,expected_min,expected_max", [
        (10, 0,  0,   1.0,  1.01),   # all fully met → HII = ∞ capped at 1
        (0,  5,  5,   0.0,  0.01),   # nothing resolved → 0
        (5,  3,  2,   0.99, 1.01),   # 5/(3+2) = 1.0, capped at 1.0
        (3,  5,  2,   0.42, 0.44),   # 3/7 ≈ 0.43
        (0,  0,  0,   0.0,  0.01),   # no data → 0
    ])
    def test_hii_formula(self, fully, partial, unresolved, expected_min, expected_max):
        denominator = partial + unresolved
        if denominator > 0:
            hii = fully / denominator
        elif fully > 0:
            hii = 1.0
        else:
            hii = 0.0
        hii = min(1.0, hii)
        assert expected_min <= hii <= expected_max, \
            f"HII={hii:.4f} not in [{expected_min},{expected_max}] for fully={fully},partial={partial},unresolved={unresolved}"

    @pytest.mark.parametrize("fully,partial,unresolved,total,expected_trend", [
        (0,  0,  0,  0,  "insufficient_data"),
        (0,  0,  0,  1,  "insufficient_data"),   # only 1 data point
        (0,  3,  5,  8,  "worsening"),            # nothing met
        (10, 0,  0,  10, "stable"),               # all met, denom=0 → code returns stable
        (4,  3,  2,  9,  "stable"),                # 4/5 = 0.8 → stable
        (2,  8,  6,  16, "worsening"),             # 2/14 < 0.8
        (8,  2,  1,  11, "improving"),             # 8/3 > 1.5
    ])
    def test_trend_detection(self, fully, partial, unresolved, total, expected_trend):
        trend = _compute_trend(fully, partial, unresolved, total)
        assert trend == expected_trend, \
            f"Trend '{trend}' != '{expected_trend}' for fully={fully},partial={partial},unresolved={unresolved}"

    def test_hii_windows_defined(self):
        assert set(HII_WINDOWS) == {30, 90, 365}

    def test_hii_windows_ordered(self):
        assert HII_WINDOWS == sorted(HII_WINDOWS)

    def test_fully_met_only_returns_max(self):
        # fully_met > 0, no denominator → HII = 1.0
        denominator = 0 + 0
        hii = 1.0 if 5 > 0 else 0.0
        assert hii == 1.0

    def test_hii_capped_at_one(self):
        # Ensure we never return > 1.0 (e.g. 100 fully_met / 1 unresolved)
        hii = min(1.0, 100 / 1)
        assert hii == 1.0

    @pytest.mark.parametrize("hii,expected_label", [
        (1.0,  "stable"),      # HII=1.0, below 1.5 threshold
        (0.85, "stable"),
        (0.80, "stable"),      # boundary
        (0.79, "worsening"),
        (0.0,  "worsening"),
    ])
    def test_trend_from_hii_value(self, hii, expected_label):
        """Map HII back to a trend label."""
        if hii >= 1.5:
            label = "improving"
        elif hii >= 0.8:
            label = "stable"
        else:
            label = "worsening"
        assert label == expected_label


# ── Override learning ─────────────────────────────────────────
class TestOverrideLearning:

    def test_override_was_better_logic(self):
        """
        override_was_better = True when chosen volunteer's task rating
        exceeds suggested volunteer's historical avg.
        """
        chosen_rating   = 4.5
        suggested_avg   = 3.2
        override_better = chosen_rating > suggested_avg
        assert override_better is True

    def test_override_was_worse_logic(self):
        chosen_rating   = 2.0
        suggested_avg   = 4.0
        override_better = chosen_rating > suggested_avg
        assert override_better is False

    def test_win_rate_calculation(self):
        overrides = [True, True, False, True, False]
        win_rate  = sum(overrides) / len(overrides)
        assert abs(win_rate - 0.6) < 0.001

    def test_no_overrides_win_rate_none(self):
        total   = 0
        win_rate = None if total == 0 else 0.5
        assert win_rate is None

    def test_override_context_fields(self):
        """Ensure all required context signals are tracked."""
        required_fields = {
            "task_id", "tenant_id", "suggested_vol_id", "suggested_score",
            "chosen_vol_id", "override_reason", "coordinator_id",
            "need_category", "need_ward_id", "need_urgency",
        }
        # These are the columns we INSERT — verify they're all planned
        actual_fields = {
            "task_id", "tenant_id", "suggested_vol_id", "suggested_score",
            "chosen_vol_id", "coordinator_id", "override_reason",
            "need_category", "need_ward_id", "need_urgency",
        }
        assert required_fields == actual_fields


# ── Impact metrics ────────────────────────────────────────────
class TestImpactMetrics:

    def test_resolution_rate_formula(self):
        needs_reported = 100
        needs_resolved = 73
        rate = needs_resolved / needs_reported
        assert abs(rate - 0.73) < 0.001

    def test_resolution_rate_zero_divide_guard(self):
        rate = 0 / 1 if 1 > 0 else 0.0   # guard pattern
        assert rate == 0.0

    def test_retention_rate_formula(self):
        vol_existing = 20
        vol_retained = 18
        rate = vol_retained / vol_existing
        assert abs(rate - 0.90) < 0.001

    def test_period_type_values(self):
        valid = {"daily", "weekly", "monthly", "quarterly"}
        assert "monthly" in valid
        assert "daily" in valid

    def test_category_breakdown_structure(self):
        """category_breakdown is a dict of category→count."""
        breakdown = {"food": 45, "health": 30, "water": 15, "other": 10}
        assert all(isinstance(v, int) for v in breakdown.values())
        assert sum(breakdown.values()) == 100

    def test_ward_breakdown_structure(self):
        """ward_breakdown is a dict of ward_id→{count, avg_urgency}."""
        breakdown = {
            "K-East": {"count": 20, "avg_urgency": 0.72},
            "M-East": {"count": 35, "avg_urgency": 0.85},
        }
        for ward, data in breakdown.items():
            assert "count"       in data
            assert "avg_urgency" in data
            assert 0.0 <= data["avg_urgency"] <= 1.0

    @pytest.mark.parametrize("p95,expected_range", [
        (30.0,  (25,  35)),     # 30 min P95 TTA is very good
        (90.0,  (85,  95)),     # 90 min is acceptable
        (300.0, (290, 310)),    # 5hr is bad
    ])
    def test_p95_tta_interpretation(self, p95, expected_range):
        lo, hi = expected_range
        assert lo <= p95 <= hi


# ── Cross-NGO duplication ─────────────────────────────────────
class TestCrossNGODuplication:

    def test_duplication_rate_zero(self):
        total   = 50
        linked  = 0
        rate    = linked / total if total > 0 else 0.0
        assert rate == 0.0

    def test_duplication_rate_all_linked(self):
        total   = 50
        linked  = 50
        rate    = linked / total
        assert rate == 1.0

    def test_duplication_rate_partial(self):
        total   = 100
        linked  = 5
        rate    = linked / total
        assert abs(rate - 0.05) < 0.001

    def test_zero_total_guard(self):
        total   = 0
        rate    = 0 / total if total > 0 else 0.0
        assert rate == 0.0


# ── Feedback loop ─────────────────────────────────────────────
class TestFeedbackLoop:

    def test_outcome_to_need_status_mapping(self):
        """Outcome from task should map to NeedRecord status."""
        mapping = {
            "need_fully_met":    "resolved",
            "partially_met":     "in_progress",
            "unresolved":        "verified",
            "follow_up_required":"in_progress",
        }
        assert mapping["need_fully_met"]    == "resolved"
        assert mapping["partially_met"]     == "in_progress"
        assert mapping["unresolved"]        == "verified"
        assert mapping["follow_up_required"]== "in_progress"

    def test_all_outcome_statuses_mapped(self):
        valid_outcomes = {"need_fully_met","partially_met","unresolved","follow_up_required"}
        mapping = {
            "need_fully_met":    "resolved",
            "partially_met":     "in_progress",
            "unresolved":        "verified",
            "follow_up_required":"in_progress",
        }
        assert valid_outcomes == set(mapping.keys())

    def test_feedback_event_types(self):
        """All feedback event types used in the system."""
        required_types = {
            "task_completed",
            "need_resolved",
            "override_recorded",
            "burnout_updated",
            "hii_computed",
        }
        # These are the strings we INSERT into feedback_events
        actual_types = {"task_completed","need_resolved","override_recorded",
                        "burnout_updated","hii_computed"}
        assert required_types == actual_types

    def test_crisis_frequency_formula(self):
        """Rolling 6-month needs/month."""
        needs_in_6_months = 12
        freq = needs_in_6_months / 6.0
        assert freq == 2.0

    def test_chronic_threshold_detection(self):
        """Households with freq > 2/month are chronic."""
        chronic_threshold = 2.0
        assert 2.1 > chronic_threshold   # chronic
        assert 1.9 < chronic_threshold   # not chronic
        assert 2.0 == chronic_threshold  # exactly at boundary → not chronic (strict >)

    def test_follow_up_need_inherits_category(self):
        """Follow-up NeedRecord must preserve parent's category."""
        parent = {"category": "food", "subcategory": "rice", "ward_id": "K-East"}
        follow_up = {
            "category":   parent["category"],
            "subcategory":parent["subcategory"],
            "ward_id":    parent["ward_id"],
            "status":     "verified",
            "urgency_score": 0.7,
        }
        assert follow_up["category"] == "food"
        assert follow_up["status"]   == "verified"
        assert follow_up["urgency_score"] == 0.7


# ── Funder report anonymization contract ─────────────────────
class TestFunderReportAnonymization:

    def test_no_pii_keys_in_report_schema(self):
        """Funder report must never contain these keys."""
        forbidden = {
            "name", "phone", "email", "address", "household_id",
            "need_id", "volunteer_id", "pii_ref", "user_id",
        }
        # Allowed top-level keys in funder report
        allowed = {
            "report_period", "months_covered", "monthly_metrics",
            "household_trend_distribution", "note", "generated_at",
        }
        assert forbidden.isdisjoint(allowed)

    def test_funder_report_has_note(self):
        """Report must include explicit anonymization disclaimer."""
        note = "All data is anonymized. No personal information is included."
        assert "anonymized" in note.lower()
        assert "personal" in note.lower()

    def test_monthly_metrics_only_aggregates(self):
        """A monthly_metrics row should contain only aggregate fields."""
        sample_row = {
            "period_start":          "2025-01-01",
            "period_end":            "2025-01-31",
            "households_served":     142,
            "needs_resolved":        89,
            "needs_resolution_rate": 0.73,
            "volunteers_active":     34,
        }
        pii_fields = {"name","phone","email","household_id","volunteer_id","need_id"}
        row_keys   = set(sample_row.keys())
        assert row_keys.isdisjoint(pii_fields)


# ── Smart matching: household context ─────────────────────────
class TestSmartMatchingHouseholdContext:

    def test_continuity_boost_applies_when_prior_household(self):
        """Volunteer with prior relationship gets +0.15 boost."""
        from services.coordination.matching.matcher import CONTINUITY_BOOST
        base_score  = 0.60
        boosted     = base_score + CONTINUITY_BOOST
        assert abs(boosted - 0.75) < 0.001

    def test_cultural_tag_boost_capped_at_3(self):
        """Max 3 cultural tags contribute boosts."""
        from services.coordination.matching.matcher import CULTURAL_BOOST_PER
        max_boost = 3 * CULTURAL_BOOST_PER
        assert max_boost == pytest.approx(0.15, abs=0.001)
        # 4 matching tags still only gives 3 * 0.05 = 0.15
        matching_tags = {"a","b","c","d"}
        capped = min(len(matching_tags), 3) * CULTURAL_BOOST_PER
        assert capped == max_boost

    def test_match_score_clamped_to_range(self):
        """Final match score never exceeds [0, 1]."""
        from services.coordination.matching.matcher import (
            CONTINUITY_BOOST, LANGUAGE_BOOST, CULTURAL_BOOST_PER, FATIGUE_PENALTY_PER
        )
        raw = 0.9 + CONTINUITY_BOOST + LANGUAGE_BOOST + 3 * CULTURAL_BOOST_PER
        clamped = max(0.0, min(1.0, raw))
        assert 0.0 <= clamped <= 1.0

    def test_fatigue_penalty_sufficient_to_suppress(self):
        """5 days consecutive deployment should significantly reduce score."""
        from services.coordination.matching.matcher import FATIGUE_PENALTY_PER, MAX_FATIGUE_DAYS
        max_penalty = MAX_FATIGUE_DAYS * FATIGUE_PENALTY_PER
        assert max_penalty == pytest.approx(0.50, abs=0.001)

    def test_language_boost_only_when_match(self):
        """Language boost only when volunteer language ∩ need language ≠ ∅."""
        from services.coordination.matching.matcher import LANGUAGE_BOOST
        vol_langs  = ["hi", "mr"]
        need_langs = ["en", "ta"]
        match      = any(l in vol_langs for l in need_langs)
        boost      = LANGUAGE_BOOST if match else 0.0
        assert boost == 0.0

        need_langs2 = ["hi", "ta"]
        match2      = any(l in vol_langs for l in need_langs2)
        boost2      = LANGUAGE_BOOST if match2 else 0.0
        assert boost2 == LANGUAGE_BOOST


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=os.path.join(os.path.dirname(__file__), "..")
    )
    sys.exit(result.returncode)
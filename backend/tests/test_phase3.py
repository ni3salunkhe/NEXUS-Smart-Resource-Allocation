"""
NEXUS Phase 3 — Volunteer Coordination Validation Tests
Tests: burnout formula, decay, matching vectors, cosine similarity,
       boosters, task state machine transitions, SMS parsing,
       notification template rendering, briefing generation
"""
import pytest
from datetime import datetime, timezone, timedelta, date

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.coordination.burnout import (
    _compute_score, _count_consecutive, _label,
    apply_rest_day_decay,
    W_FREQ_7D, W_FREQ_30D, W_CONSEC, W_OUTCOME,
    EXCLUDED_THRESHOLD, WARNING_THRESHOLD, MODERATE_THRESHOLD,
    DECAY_PER_REST_DAY,
)
from services.coordination.matching.matcher import (
    _build_requirement_vector, _build_capability_vector,
    _cosine_similarity, MatchCandidate,
    CONTINUITY_BOOST, LANGUAGE_BOOST, CULTURAL_BOOST_PER,
    FATIGUE_PENALTY_PER, CATEGORY_SKILL_HINTS,
)
from services.coordination.task_service import VALID_TRANSITIONS
from services.coordination.notifications.service import (
    parse_sms_response, _build_message, BRIEFING_TEMPLATES,
)


# ── Burnout: formula ──────────────────────────────────────────
class TestBurnoutFormula:
    def test_weights_sum_to_one(self):
        total = W_FREQ_7D + W_FREQ_30D + W_CONSEC + W_OUTCOME
        assert abs(total - 1.0) < 0.001

    def test_zero_deployments_zero_score(self):
        score = _compute_score(0, 0, 0, 5.0)  # 5.0 rating = 0 outcome penalty
        assert score == 0.0

    def test_max_deployments_high_score(self):
        score = _compute_score(7, 20, 7, 1.0)  # worst case
        assert score >= 0.85

    def test_daily_deployment_score(self):
        """1 deployment/day for 7d, 15 for 30d, 5 consecutive, avg 3.0 rating."""
        score = _compute_score(7, 15, 5, 3.0)
        assert 0.50 < score < 0.90

    @pytest.mark.parametrize("d7,d30,consec,rating,min_s,max_s", [
        (0, 0, 0, 5.0, 0.0, 0.05),    # fully rested, great ratings
        (1, 4, 1, 4.0, 0.05, 0.25),   # light load
        (4, 12, 4, 3.0, 0.35, 0.65),  # moderate load
        (7, 20, 7, 1.0, 0.85, 1.01),  # maximum burnout
    ])
    def test_score_ranges(self, d7, d30, consec, rating, min_s, max_s):
        score = _compute_score(d7, d30, consec, rating)
        assert min_s <= score <= max_s, \
            f"Score {score:.3f} not in [{min_s},{max_s}] for d7={d7},d30={d30},consec={consec}"

    def test_score_clamped_to_one(self):
        score = _compute_score(100, 100, 100, 0.0)
        assert score <= 1.0

    @pytest.mark.parametrize("score,expected_label", [
        (0.85, "critical"),
        (0.80, "critical"),
        (0.79, "warning"),
        (0.65, "warning"),
        (0.64, "moderate"),
        (0.50, "moderate"),
        (0.49, "healthy"),
        (0.00, "healthy"),
    ])
    def test_label_boundaries(self, score, expected_label):
        assert _label(score) == expected_label

    def test_thresholds_ordered(self):
        assert EXCLUDED_THRESHOLD > WARNING_THRESHOLD > MODERATE_THRESHOLD > 0

    def test_threshold_values(self):
        assert EXCLUDED_THRESHOLD == 0.80
        assert WARNING_THRESHOLD  == 0.65
        assert MODERATE_THRESHOLD == 0.50


# ── Burnout: consecutive day counting ────────────────────────
class TestConsecutiveDays:
    def test_no_deployments(self):
        assert _count_consecutive([], date.today()) == 0

    def test_deployed_today(self):
        today  = date.today()
        result = _count_consecutive([today], today)
        assert result == 1

    def test_deployed_3_consecutive(self):
        today  = date.today()
        dates  = [today, today - timedelta(1), today - timedelta(2)]
        result = _count_consecutive(dates, today)
        assert result == 3

    def test_gap_breaks_streak(self):
        today = date.today()
        dates = [today, today - timedelta(2)]  # gap on day -1
        result = _count_consecutive(dates, today)
        assert result == 1

    def test_only_past_dates(self):
        today  = date.today()
        dates  = [today - timedelta(3), today - timedelta(4)]
        result = _count_consecutive(dates, today)
        assert result == 0   # streak ended 3 days ago


# ── Burnout: rest day decay ───────────────────────────────────
class TestRestDayDecay:
    def test_no_rest_no_decay(self):
        assert apply_rest_day_decay(0.75, 0) == 0.75

    def test_one_rest_day(self):
        result = apply_rest_day_decay(0.75, 1)
        assert abs(result - (0.75 - DECAY_PER_REST_DAY)) < 0.001

    def test_enough_rest_reaches_zero(self):
        result = apply_rest_day_decay(0.60, 10)
        assert result == 0.0

    def test_decay_does_not_go_negative(self):
        result = apply_rest_day_decay(0.10, 5)
        assert result >= 0.0


# ── Matching: vector building ─────────────────────────────────
class TestMatchingVectors:
    def test_requirement_vector_has_skill_dims(self):
        vec = _build_requirement_vector("health", None, ["en"], [])
        assert any(k.startswith("skill:") for k in vec)

    def test_health_category_requires_medical(self):
        vec = _build_requirement_vector("health", None, ["en"], [])
        assert "skill:medical" in vec

    def test_legal_category_requires_legal_skill(self):
        vec = _build_requirement_vector("legal", None, ["hi"], [])
        assert "skill:legal" in vec

    def test_language_dims_in_vector(self):
        vec = _build_requirement_vector("food", None, ["hi", "mr"], [])
        assert "lang:hi" in vec
        assert "lang:mr" in vec

    def test_cultural_tags_in_vector(self):
        vec = _build_requirement_vector("food", None, [], ["muslim", "tribal"])
        assert "culture:muslim" in vec

    def test_capability_vector_skill_dims(self):
        vec = _build_capability_vector(
            skills=["medical", "counselling"],
            skill_proficiency={"medical": "certified"},
            preferred_language=["en", "hi"],
            cultural_context_tags=[],
        )
        assert "skill:medical" in vec
        assert "skill:counselling" in vec

    def test_skill_proficiency_scales_value(self):
        beginner  = _build_capability_vector(["medical"], {"medical": "beginner"}, [], [])
        certified = _build_capability_vector(["medical"], {"medical": "certified"}, [], [])
        assert certified["skill:medical"] > beginner["skill:medical"]


# ── Matching: cosine similarity ───────────────────────────────
class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = {"a": 1.0, "b": 0.5}
        assert abs(_cosine_similarity(v, v) - 1.0) < 0.001

    def test_orthogonal_vectors(self):
        a = {"x": 1.0}
        b = {"y": 1.0}
        assert _cosine_similarity(a, b) == 0.0

    def test_partial_overlap(self):
        a = {"medical": 1.0, "legal": 0.5}
        b = {"medical": 1.0, "transport": 0.8}
        score = _cosine_similarity(a, b)
        assert 0 < score < 1.0

    def test_empty_vectors(self):
        assert _cosine_similarity({}, {}) == 0.0
        assert _cosine_similarity({"a": 1.0}, {}) == 0.0

    def test_symmetry(self):
        a = {"x": 1.0, "y": 0.5}
        b = {"x": 0.5, "z": 1.0}
        assert abs(_cosine_similarity(a, b) - _cosine_similarity(b, a)) < 0.0001


# ── Matching: boosters ────────────────────────────────────────
class TestMatchingBoosters:
    def test_continuity_boost_constant(self):
        assert CONTINUITY_BOOST == 0.15

    def test_language_boost_constant(self):
        assert LANGUAGE_BOOST == 0.10

    def test_cultural_boost_per_tag(self):
        assert CULTURAL_BOOST_PER == 0.05

    def test_fatigue_penalty_per_day(self):
        assert FATIGUE_PENALTY_PER == 0.10

    def test_all_category_hints_defined(self):
        required = {"food","health","water","shelter","education",
                    "livelihood","mental_health","legal","hygiene","other"}
        assert required.issubset(set(CATEGORY_SKILL_HINTS.keys()))

    def test_match_candidate_to_dict(self):
        c = MatchCandidate(
            volunteer_id="v1", match_score=0.85, cosine_score=0.70,
            boosts_applied={"language": 0.10}, fatigue_penalty=0.0,
            distance_km=3.5,
        )
        d = c.to_dict()
        assert d["match_score"]  == pytest.approx(0.85, abs=0.001)
        assert d["distance_km"]  == pytest.approx(3.5,  abs=0.001)
        assert "boosts_applied"  in d


# ── Task state machine ────────────────────────────────────────
class TestTaskStateMachine:
    def test_all_states_defined(self):
        required = {"unassigned","dispatched","accepted","in_progress",
                    "completed","cancelled","needs_reassignment","closed"}
        assert required == set(VALID_TRANSITIONS.keys())

    def test_terminal_state_has_no_transitions(self):
        assert VALID_TRANSITIONS["closed"] == []

    def test_unassigned_can_only_dispatch(self):
        assert VALID_TRANSITIONS["unassigned"] == ["dispatched"]

    def test_dispatched_can_accept_or_cancel(self):
        allowed = set(VALID_TRANSITIONS["dispatched"])
        assert "accepted" in allowed
        assert "needs_reassignment" in allowed
        assert "cancelled" in allowed

    def test_completed_goes_to_closed(self):
        assert "closed" in VALID_TRANSITIONS["completed"]

    def test_needs_reassignment_goes_to_dispatched(self):
        assert "dispatched" in VALID_TRANSITIONS["needs_reassignment"]

    def test_in_progress_can_complete_or_reassign(self):
        allowed = VALID_TRANSITIONS["in_progress"]
        assert "completed" in allowed
        assert "needs_reassignment" in allowed

    def test_no_backward_transitions_from_terminal(self):
        """Closed tasks cannot go back to any state."""
        assert len(VALID_TRANSITIONS["closed"]) == 0

    @pytest.mark.parametrize("state", [
        "unassigned","dispatched","accepted","in_progress",
        "completed","cancelled","needs_reassignment","closed"
    ])
    def test_all_states_have_transition_list(self, state):
        assert isinstance(VALID_TRANSITIONS[state], list)


# ── SMS parsing ───────────────────────────────────────────────
class TestSMSParsing:
    @pytest.mark.parametrize("body,expected_action", [
        ("1",       "accept"),
        ("yes",     "accept"),
        ("YES",     "accept"),
        ("ok",      "accept"),
        ("haan",    "accept"),
        ("ha",      "accept"),
        ("accept",  "accept"),
        ("2",       "decline"),
        ("no",      "decline"),
        ("NO",      "decline"),
        ("decline", "decline"),
        ("nahi",    "decline"),
        ("busy",    "decline"),
        ("xyz",     "unknown"),
        ("maybe",   "unknown"),
        ("",        "unknown"),
    ])
    def test_sms_action_parsing(self, body, expected_action):
        action, _ = parse_sms_response(body)
        assert action == expected_action, f"Body '{body}' → expected '{expected_action}', got '{action}'"

    def test_decline_with_reason(self):
        action, reason = parse_sms_response("2 sick today")
        assert action == "decline"
        assert "sick" in reason

    def test_whitespace_trimmed(self):
        action, _ = parse_sms_response("  1  ")
        assert action == "accept"


# ── Notification templates ────────────────────────────────────
class TestNotificationTemplates:
    def test_all_languages_defined(self):
        required = {"en", "hi", "mr", "ta"}
        assert required.issubset(set(BRIEFING_TEMPLATES.keys()))

    def test_all_template_keys_present(self):
        required = {"dispatch", "accepted", "reminder", "completed"}
        for lang, templates in BRIEFING_TEMPLATES.items():
            assert required.issubset(set(templates.keys())), \
                f"Language '{lang}' missing template keys"

    def test_dispatch_template_has_placeholders(self):
        tmpl = BRIEFING_TEMPLATES["en"]["dispatch"]
        assert "{category}"         in tmpl
        assert "{location}"         in tmpl
        assert "{beneficiary_count}" in tmpl

    def test_message_build_interpolates(self):
        msg = _build_message("dispatch", "en", {
            "category":          "food",
            "location":          "Ward 5",
            "beneficiary_count": 6,
            "description":       "Family needs rice",
        })
        assert "food"       in msg
        assert "Ward 5"     in msg
        assert "6"          in msg

    def test_hindi_dispatch_template(self):
        msg = _build_message("dispatch", "hi", {
            "category":          "food",
            "location":          "वार्ड 5",
            "beneficiary_count": 4,
            "description":       "परिवार को खाना चाहिए",
        })
        assert "food" in msg or "वार्ड" in msg

    def test_fallback_to_english_for_unknown_lang(self):
        msg = _build_message("dispatch", "xx", {
            "category":          "water",
            "location":          "Dharavi",
            "beneficiary_count": 10,
            "description":       "No water",
        })
        # Should fall back gracefully (return english or empty, not crash)
        assert isinstance(msg, str)

    def test_missing_variable_doesnt_crash(self):
        """If a variable is missing, message still returns (partial)."""
        msg = _build_message("dispatch", "en", {"category": "food"})
        assert isinstance(msg, str)


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=os.path.join(os.path.dirname(__file__), "..")
    )
    sys.exit(result.returncode)
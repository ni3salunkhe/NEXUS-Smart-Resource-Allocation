"""
NEXUS Phase 1 — Ingestion Pipeline Validation Tests
Tests: NLP extraction, severity scoring, geocoding logic,
       deduplication similarity, pipeline routing
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.ingestion.processors.nlp import (
    extract_nlp, _classify_category, _score_severity,
    _extract_vulnerability_flags, _extract_beneficiary_count,
    _extract_locations, _normalize_text,
)
from services.ingestion.processors.geocoding import (
    _normalize_location_text, _lookup_custom_landmarks,
)
from services.ingestion.processors.deduplication import (
    _tokenize as dedup_tokenize, _jaccard_sim,
    should_route_to_review, compute_review_priority,
    NLP_CONFIDENCE_REVIEW, SIMILARITY_THRESHOLD,
)


# ── NLP: Category classification ─────────────────────────────
class TestCategoryClassification:
    @pytest.mark.parametrize("text,expected_cat", [
        ("The family has no food and children are hungry", "food"),
        ("Child has high fever and needs medicine immediately", "health"),
        ("There is no drinking water in the area", "water"),
        ("The roof collapsed in the rain, family has no shelter", "shelter"),
        ("Children dropped out of school, need school fees", "education"),
        ("Family lost livelihood, no job and no income", "livelihood"),
        ("Person showing signs of depression and severe anxiety", "mental_health"),
        ("No ration card, cannot get government benefits legal help needed", "legal"),
        ("No toilet, sanitation very poor hygiene issues", "hygiene"),
        ("Something vague and ambiguous with no clear need", "other"),
    ])
    def test_category_detection(self, text, expected_cat):
        cat, _, _ = _classify_category(text)
        assert cat == expected_cat, f"Expected '{expected_cat}', got '{cat}' for: {text[:60]}"

    def test_returns_confidence_score(self):
        _, _, conf = _classify_category("family is starving and has no food")
        assert 0.0 <= conf <= 1.0

    def test_multilingual_food_keywords(self):
        # Hinglish / transliterated
        cat, _, _ = _classify_category("bacha bhukha hai, khana chahiye")
        assert cat == "food"

    def test_multilingual_health_keywords(self):
        cat, _, _ = _classify_category("bimaar hai, bukhar hai, dawa chahiye")
        assert cat == "health"

    def test_subcategory_populated(self):
        _, subcat, _ = _classify_category("family needs rice and grain food supply")
        assert subcat is not None


# ── NLP: Severity scoring ─────────────────────────────────────
class TestSeverityScoring:
    @pytest.mark.parametrize("text,min_score,max_score", [
        ("Child is dying, emergency, no food for three days", 0.90, 1.0),
        ("Family is starving, critical condition urgent help needed", 0.75, 1.0),
        ("Family is very sick and struggling with the issue", 0.45, 0.75),
        ("There is a small problem with water supply", 0.20, 0.55),
        ("General information about the area", 0.0, 0.45),
    ])
    def test_severity_ranges(self, text, min_score, max_score):
        score = _score_severity(text)
        assert min_score <= score <= max_score, \
            f"Score {score:.2f} not in [{min_score}, {max_score}] for: {text[:50]}"

    def test_no_text_returns_default(self):
        score = _score_severity("")
        assert score == 0.35

    def test_multiple_high_signals(self):
        text = "dying emergency critical immediately cannot survive"
        assert _score_severity(text) >= 0.90


# ── NLP: Vulnerability flags ──────────────────────────────────
class TestVulnerabilityExtraction:
    def test_child_flag(self):
        flags = _extract_vulnerability_flags("family with three children and a baby")
        assert flags.get("has_child") is True

    def test_elderly_flag(self):
        flags = _extract_vulnerability_flags("old man living alone, budhaa aadmi")
        assert flags.get("has_elderly") is True

    def test_pregnant_flag(self):
        flags = _extract_vulnerability_flags("pregnant woman needs medical help garbhavati")
        assert flags.get("has_pregnant") is True

    def test_disabled_flag(self):
        flags = _extract_vulnerability_flags("disabled person in wheelchair needs support")
        assert flags.get("has_disabled") is True

    def test_no_flags(self):
        flags = _extract_vulnerability_flags("adult male, working age, needs job")
        assert not any(flags.values())

    def test_multiple_flags(self):
        flags = _extract_vulnerability_flags(
            "elderly woman with chronic illness and a pregnant daughter"
        )
        assert flags.get("has_elderly") is True
        assert flags.get("has_pregnant") is True
        assert flags.get("chronic_illness") is True

    def test_all_flags_present_in_output(self):
        flags = _extract_vulnerability_flags("test")
        required = {"has_child","has_elderly","has_disabled","has_pregnant","chronic_illness"}
        assert required.issubset(set(flags.keys()))


# ── NLP: Beneficiary count ────────────────────────────────────
class TestBeneficiaryExtraction:
    @pytest.mark.parametrize("text,expected", [
        ("family of 5 needs help", 5),
        ("10 people in the household", 10),
        ("3 children dropped out of school", 3),
        ("two families, about 12 members", 12),
        ("single adult male", 1),
        ("15 individuals affected", 15),
    ])
    def test_beneficiary_count(self, text, expected):
        count = _extract_beneficiary_count(text)
        assert count == expected, f"Expected {expected}, got {count} for: '{text}'"


# ── NLP: Location extraction ──────────────────────────────────
class TestLocationExtraction:
    def test_extracts_near_landmark(self):
        locations = _extract_locations("The family lives near the dargah on the main road")
        assert len(locations) >= 1
        assert any("dargah" in loc.text.lower() or "dargah" in str(loc.landmark_tags) for loc in locations)

    def test_extracts_ward_reference(self):
        locations = _extract_locations("In ward 7, near the school building")
        assert len(locations) >= 1

    def test_no_location_text(self):
        locations = _extract_locations("Family needs food and medicine urgently")
        assert len(locations) == 0

    def test_landmark_tags_generated(self):
        locations = _extract_locations("Behind the blue building at the pump corner")
        for loc in locations:
            assert isinstance(loc.landmark_tags, list)

    def test_max_3_locations(self):
        text = ("Near the pump. Beside the temple. Behind the school. "
                "Opposite the hospital. Next to the mosque.")
        locations = _extract_locations(text)
        assert len(locations) <= 3


# ── NLP: Full pipeline ────────────────────────────────────────
class TestFullNLPPipeline:
    def test_full_extraction(self):
        text = ("Family of 6 near the dargah in ward 5. Children are hungry "
                "for 3 days. Elderly woman is very sick. Emergency help needed immediately.")
        out = extract_nlp(text)
        assert out.category in ("food", "health")
        assert out.severity_score >= 0.75
        assert out.beneficiary_count == 6
        assert out.vulnerability_flags.get("has_child") is True
        assert out.vulnerability_flags.get("has_elderly") is True
        assert len(out.locations) >= 1
        assert out.confidence > 0.3

    def test_empty_text(self):
        out = extract_nlp("")
        assert out.confidence == 0.0
        assert out.category is None

    def test_text_normalized(self):
        out = extract_nlp("  Multiple   spaces   and\ttabs\n")
        assert "  " not in (out.description_normalized or "")

    def test_hindi_language_detected(self):
        # Devanagari character range test
        out = extract_nlp("परिवार को खाना चाहिए, बच्चे भूखे हैं")
        assert out.language_detected == "hi"


# ── Geocoding ─────────────────────────────────────────────────
class TestGeocoding:
    def test_normalize_location_text(self):
        assert _normalize_location_text("Near the DARGAH!") == "near the dargah"
        assert _normalize_location_text("  Dharavi,  Mumbai  ") == "dharavi  mumbai".replace("  ", " ")

    def test_custom_landmark_lookup_dharavi(self):
        result = _lookup_custom_landmarks("family lives in dharavi slum")
        assert result is not None
        assert result.latitude is not None
        assert result.confidence >= 0.7
        assert result.resolved_by == "custom"

    def test_custom_landmark_govandi(self):
        result = _lookup_custom_landmarks("near govandi station")
        assert result is not None
        assert result.ward_id == "M-East"

    def test_unknown_location_returns_none(self):
        result = _lookup_custom_landmarks("completely unknown location xyz")
        assert result is None

    def test_landmark_without_coords_returns_none(self):
        # "near dargah" is in table but has no coords
        result = _lookup_custom_landmarks("near dargah")
        assert result is None


# ── Deduplication ─────────────────────────────────────────────
class TestDeduplication:
    def test_identical_text(self):
        sim = _jaccard_sim("family needs food urgently", "family needs food urgently")
        assert sim == 1.0

    def test_completely_different(self):
        sim = _jaccard_sim("family needs food", "water pipeline broken")
        assert sim < 0.1

    def test_similar_text_above_threshold(self):
        a = "family of 5 near the pump has no food for three days"
        b = "family near the pump needs food three days no food"
        sim = _jaccard_sim(a, b)
        assert sim >= 0.70

    def test_tokenizer_removes_stopwords(self):
        tokens = dedup_tokenize("the family is in the area")
        assert "the" not in tokens
        assert "is"  not in tokens
        assert "family" in tokens

    @pytest.mark.parametrize("confidence,hints,expected", [
        (0.60, [],                          True),   # low confidence
        (0.80, ["household_resolution"],    True),   # has hints
        (0.90, [],                          False),  # high confidence, no hints
        (0.74, [],                          True),   # below threshold
        (0.75, [],                          False),  # exactly at threshold
    ])
    def test_review_routing(self, confidence, hints, expected):
        assert should_route_to_review(confidence, hints) == expected

    @pytest.mark.parametrize("nlp_conf,severity,has_hh,expected_range", [
        (0.3, 0.9, False, (1, 2)),    # high severity, low confidence, no household → priority 1
        (0.3, 0.5, True,  (2, 3)),    # low confidence, medium severity
        (0.6, 0.3, True,  (4, 6)),    # medium confidence, low severity
        (0.9, 0.1, True,  (7, 9)),    # high confidence, low severity → low priority
    ])
    def test_review_priority(self, nlp_conf, severity, has_hh, expected_range):
        p = compute_review_priority(nlp_conf, severity, has_hh)
        lo, hi = expected_range
        assert lo <= p <= hi, f"Priority {p} not in [{lo},{hi}]"

    def test_threshold_constants_sane(self):
        assert 0.5 < NLP_CONFIDENCE_REVIEW < 1.0
        assert 0.5 < SIMILARITY_THRESHOLD  < 1.0


# ── Pipeline payload ──────────────────────────────────────────
class TestIngestionPayload:
    def test_payload_creation(self):
        from services.ingestion.pipeline import IngestionPayload
        p = IngestionPayload(
            source_type="mobile",
            tenant_id="tenant-001",
            submitted_by="user-001",
            raw_text="Family needs food near the pump",
        )
        assert p.source_type == "mobile"
        assert p.raw_text is not None

    def test_payload_with_prefilled(self):
        from services.ingestion.pipeline import IngestionPayload
        p = IngestionPayload(
            source_type="mobile",
            tenant_id="t1",
            submitted_by="u1",
            raw_text="Test",
            prefilled_category="food",
            prefilled_beneficiary=5,
            known_household_id="hh-001",
        )
        assert p.prefilled_category == "food"
        assert p.prefilled_beneficiary == 5
        assert p.known_household_id == "hh-001"


# ── OCR preprocessing (without cv2) ───────────────────────────
class TestOCRModule:
    def test_preprocess_no_cv2(self):
        """When cv2 absent, pass-through returns same bytes."""
        from services.ingestion.processors.ocr import preprocess_image
        sample = b"fake_image_bytes"
        result = preprocess_image(sample)
        # Either returns same bytes (no cv2) or processes it (cv2 available)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_ocr_result_dataclass(self):
        from services.ingestion.processors.ocr import OCRResult
        r = OCRResult(
            text="Family needs food",
            confidence=0.85,
            language_hints=["en", "hi"],
            engine_used="vision",
        )
        assert r.text == "Family needs food"
        assert r.confidence == 0.85

    def test_audio_transcript_wrap(self):
        from services.ingestion.processors.ocr import extract_text_from_audio_transcript
        result = extract_text_from_audio_transcript("Family near the pump needs water")
        assert result.engine_used == "speech_to_text"
        assert result.confidence == 0.85
        assert "water" in result.text


if __name__ == "__main__":
    import subprocess
    result = subprocess.run(
        ["python", "-m", "pytest", __file__, "-v", "--tb=short"],
        cwd=os.path.join(os.path.dirname(__file__), "..")
    )
    sys.exit(result.returncode)
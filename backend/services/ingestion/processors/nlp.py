"""
NLP Processor
Pipeline: raw text → structured NLP output
- Language detection
- Named Entity Recognition (location, person, need type)
- Need category + subcategory classification
- Severity signal extraction
- Beneficiary extraction
- Description embedding (sentence-BERT stub; plug in real model)
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Optional NLP library imports ──────────────────────────────
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    logger.warning("spaCy not installed — using rule-based NLP fallback")

try:
    from langdetect import detect as detect_language
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False


# ── Output dataclasses ────────────────────────────────────────
@dataclass
class LocationEntity:
    text: str               # raw mention: "near the dargah"
    normalized: str         # cleaned: "near dargah"
    landmark_tags: list[str] = field(default_factory=list)
    confidence: float = 0.5


@dataclass
class NLPOutput:
    # Classification
    category:           Optional[str] = None   # enum value
    subcategory:        Optional[str] = None
    # Severity
    severity_score:     float = 0.5            # 0.0 – 1.0
    # Entities
    locations:          list[LocationEntity] = field(default_factory=list)
    beneficiary_count:  int = 1
    vulnerability_flags: dict = field(default_factory=dict)
    # Text
    description_normalized: Optional[str] = None
    language_detected:  str = "en"
    # Quality
    confidence:         float = 0.0            # overall NLP confidence
    entities_raw:       dict = field(default_factory=dict)


# ── Keyword maps ──────────────────────────────────────────────
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "food": [
        "food", "hunger", "hungry", "eat", "eating", "ration", "grain",
        "rice", "wheat", "dal", "starving", "starvation", "khana", "bhojan",
        "anaaj", "roti", "anaj", "khaana", "bhukha", "unnutrition",
        # Hindi/Marathi hints transliterated
        "bhojan", "anna", "khichdi", "midday meal",
    ],
    "health": [
        "sick", "ill", "disease", "fever", "medicine", "hospital", "doctor",
        "medical", "injury", "pain", "diarrhea", "vomiting", "pregnant",
        "child birth", "bimaar", "dawai", "dawa", "bukhar", "hospital",
        "clinic", "vaccination", "ambulance", "emergency",
    ],
    "water": [
        "water", "drinking", "tap", "well", "pipeline", "contaminated",
        "dirty water", "no water", "paani", "pani", "jal", "neer",
    ],
    "shelter": [
        "shelter", "house", "home", "roof", "tent", "homeless", "evicted",
        "flood damage", "collapsed", "wall", "ghar", "makaan", "chhat",
    ],
    "education": [
        "school", "education", "children school", "dropout", "fees",
        "books", "uniform", "teacher", "vidya", "shala", "paathshala",
    ],
    "livelihood": [
        "job", "work", "employment", "income", "wage", "salary", "farm",
        "crop", "business", "livelihood", "rozgaar", "kaam", "naukri",
    ],
    "mental_health": [
        "mental", "depression", "anxiety", "trauma", "stress", "suicide",
        "self-harm", "counselling", "therapy", "psychological",
    ],
    "legal": [
        "legal", "court", "document", "ration card", "aadhar", "certificate",
        "rights", "eviction", "police", "FIR", "complaint", "dakhila",
    ],
    "hygiene": [
        "toilet", "sanitation", "hygiene", "soap", "clean", "garbage",
        "drainage", "sewage", "shauchalaya", "safai",
    ],
}

SEVERITY_HIGH: list[str] = [
    "dying", "dead", "death", "emergency", "critical", "urgent",
    "immediately", "no food", "starving", "collapsed", "unconscious",
    "life-threatening", "serious", "severe", "crisis", "cannot",
    "days", "three days", "four days", "week without",
]

SEVERITY_MEDIUM: list[str] = [
    "very sick", "high fever", "needs help", "struggling", "difficult",
    "problem", "issue", "concern", "required", "necessary",
]

VULNERABILITY_PATTERNS: dict[str, list[str]] = {
    "has_child":    ["child", "children", "baby", "infant", "minor",
                     "bacha", "bachcha", "beta", "beti"],
    "has_elderly":  ["elderly", "old man", "old woman", "senior",
                     "budhaa", "budhiya", "aged"],
    "has_disabled": ["disabled", "handicapped", "wheelchair", "blind",
                     "deaf", "divyang", "apang"],
    "has_pregnant": ["pregnant", "pregnancy", "expecting", "garbhavati",
                     "delivery", "maternity"],
    "chronic_illness": ["chronic", "diabetes", "TB", "tuberculosis",
                        "cancer", "HIV", "long-term illness"],
}

BENEFICIARY_PATTERNS = [
    r"(\d+)\s*(?:people|persons|families|members|individuals|households?)",
    r"family\s+of\s+(\d+)",
    r"(\d+)\s+(?:adults?|children|kids?)",
]

LOCATION_INDICATORS = [
    "near", "behind", "opposite", "next to", "beside", "in front of",
    "at", "around", "ward", "slum", "area", "lane", "gali",
    "mohalla", "nagar", "colony", "chawl", "basti",
]


def _detect_language(text: str) -> str:
    if not LANGDETECT_AVAILABLE:
        # Simple heuristic: presence of Devanagari Unicode range
        if any('\u0900' <= c <= '\u097F' for c in text):
            return "hi"
        return "en"
    try:
        return detect_language(text)
    except Exception:
        return "en"


def _classify_category(text: str) -> tuple[Optional[str], Optional[str], float]:
    text_lower = text.lower()
    scores: dict[str, int] = {}

    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[category] = score

    if not scores:
        return "other", None, 0.4

    best_cat = max(scores, key=scores.get)
    best_score = scores[best_cat]
    total_kw = len(CATEGORY_KEYWORDS[best_cat])
    confidence = min(0.95, 0.5 + (best_score / total_kw) * 0.5)

    # Subcategory: top matching keyword
    matches = [kw for kw in CATEGORY_KEYWORDS[best_cat] if kw in text_lower]
    subcategory = matches[0] if matches else None

    return best_cat, subcategory, confidence


def _score_severity(text: str) -> float:
    text_lower = text.lower()

    high_hits = sum(1 for s in SEVERITY_HIGH   if s in text_lower)
    med_hits  = sum(1 for s in SEVERITY_MEDIUM if s in text_lower)

    if high_hits >= 2:
        return 0.95
    if high_hits == 1:
        return 0.80
    if med_hits >= 2:
        return 0.60
    if med_hits == 1:
        return 0.50
    return 0.35


def _extract_vulnerability_flags(text: str) -> dict:
    text_lower = text.lower()
    flags: dict[str, bool] = {}
    for flag, keywords in VULNERABILITY_PATTERNS.items():
        flags[flag] = any(kw in text_lower for kw in keywords)
    return flags


def _extract_beneficiary_count(text: str) -> int:
    for pattern in BENEFICIARY_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except (ValueError, IndexError):
                pass
    # Look for isolated numbers 2-50 near people-words
    m = re.search(r'\b([2-9]|[1-4][0-9]|50)\b', text)
    if m:
        return int(m.group(1))
    return 1


def _extract_locations(text: str) -> list[LocationEntity]:
    """
    Rule-based location extraction.
    In production: replaced by spaCy NER + Google Maps resolution.
    """
    locations = []
    sentences = re.split(r'[.!?;\n]', text)

    for sentence in sentences:
        sentence = sentence.strip()
        sentence_lower = sentence.lower()

        has_indicator = any(ind in sentence_lower for ind in LOCATION_INDICATORS)
        if not has_indicator:
            continue

        # Extract the location phrase after an indicator word
        for indicator in LOCATION_INDICATORS:
            pattern = rf'\b{re.escape(indicator)}\b\s+([A-Za-z0-9\s\-,\']+?)(?:[,;.]|$)'
            m = re.search(pattern, sentence, re.IGNORECASE)
            if m:
                loc_text = m.group(1).strip()
                if 3 <= len(loc_text) <= 80:
                    # Generate landmark tags: split into words, filter stopwords
                    tags = [w.lower() for w in loc_text.split()
                            if len(w) > 2 and w.lower() not in
                            {"the", "and", "or", "in", "at", "of", "a", "an"}]
                    locations.append(LocationEntity(
                        text=f"{indicator} {loc_text}",
                        normalized=loc_text.lower(),
                        landmark_tags=tags,
                        confidence=0.6,
                    ))
                    break  # one location per sentence

    return locations[:3]  # max 3 location entities


def _normalize_text(text: str) -> str:
    """Light cleaning: collapse whitespace, fix punctuation."""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s.,!?;:\-\'\"()]', ' ', text)
    return text.strip()


# ── spaCy-based processing (when available) ───────────────────
_nlp_model = None

def _get_spacy_model():
    global _nlp_model
    if not SPACY_AVAILABLE or _nlp_model is not None:
        return _nlp_model
    try:
        _nlp_model = spacy.load("en_core_web_sm")
        logger.info("spaCy model loaded: en_core_web_sm")
    except OSError:
        logger.warning("spaCy model not found — using rule-based NLP only")
    return _nlp_model


def _spacy_extract(text: str, nlp) -> dict:
    doc = nlp(text)
    entities = {}
    for ent in doc.ents:
        label = ent.label_
        if label not in entities:
            entities[label] = []
        entities[label].append(ent.text)
    return entities


# ── Main NLP entry point ──────────────────────────────────────
def extract_nlp(text: str) -> NLPOutput:
    """
    Full NLP extraction pipeline.
    Input:  raw text (OCR output or direct input)
    Output: NLPOutput with all extracted fields
    """
    if not text or not text.strip():
        return NLPOutput(confidence=0.0)

    # Language detection
    lang = _detect_language(text)

    # Normalize
    normalized = _normalize_text(text)

    # Category classification
    category, subcategory, cat_confidence = _classify_category(normalized)

    # Severity scoring
    severity = _score_severity(normalized)

    # Vulnerability flags
    vuln_flags = _extract_vulnerability_flags(normalized)

    # Beneficiary count
    beneficiary_count = _extract_beneficiary_count(normalized)

    # Location extraction
    locations = _extract_locations(normalized)

    # spaCy supplement (if available)
    entities_raw = {}
    nlp_model = _get_spacy_model()
    if nlp_model:
        try:
            entities_raw = _spacy_extract(normalized, nlp_model)
        except Exception as e:
            logger.debug(f"spaCy extraction error (non-fatal): {e}")

    # Overall confidence = category_confidence weighted with extraction richness
    extraction_richness = min(1.0, (
        (0.3 if locations      else 0.0) +
        (0.3 if beneficiary_count > 1 else 0.0) +
        (0.2 if any(vuln_flags.values()) else 0.0) +
        (0.2 if severity != 0.5 else 0.0)
    ))
    overall_confidence = cat_confidence * 0.7 + extraction_richness * 0.3

    return NLPOutput(
        category=category,
        subcategory=subcategory,
        severity_score=severity,
        locations=locations,
        beneficiary_count=beneficiary_count,
        vulnerability_flags=vuln_flags,
        description_normalized=normalized,
        language_detected=lang,
        confidence=overall_confidence,
        entities_raw=entities_raw,
    )
"""
OCR Processor
Pipeline: raw image bytes → preprocessed image → OCR text
Stage 1: OpenCV — deskew, CLAHE contrast, denoise, binarize
Stage 2: Google Cloud Vision API (primary, multilingual handwriting)
Stage 3: Tesseract (fallback, self-hosted)
"""
import base64
import io
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ── Optional imports (graceful degradation in dev) ────────────
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("cv2 not installed — image preprocessing disabled")

try:
    import pytesseract
    from PIL import Image as PILImage
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract not installed — Tesseract fallback disabled")

try:
    from google.cloud import vision as gvision
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    logger.warning("google-cloud-vision not installed — Vision API disabled")


@dataclass
class OCRResult:
    text: str
    confidence: float          # 0.0 – 1.0
    language_hints: list[str]  # detected languages
    engine_used: str           # "vision" | "tesseract" | "passthrough"
    raw_response: Optional[dict] = None


# ── Image preprocessing ────────────────────────────────────────
def preprocess_image(image_bytes: bytes) -> bytes:
    """
    OpenCV preprocessing pipeline:
    1. Decode → grayscale
    2. Deskew (Hough transform on edges)
    3. CLAHE contrast enhancement
    4. Gaussian denoise
    5. Otsu binarization
    Returns: processed image bytes (PNG)
    """
    if not CV2_AVAILABLE:
        return image_bytes  # pass through if cv2 absent

    nparr = np.frombuffer(image_bytes, np.uint8)
    img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        logger.warning("cv2 could not decode image — passing through raw bytes")
        return image_bytes

    # 1. Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Deskew via Hough line transform
    gray = _deskew(gray)

    # 3. CLAHE contrast
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray  = clahe.apply(gray)

    # 4. Gaussian denoise
    gray = cv2.GaussianBlur(gray, (3, 3), 0)

    # 5. Otsu binarization
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Encode back to PNG
    success, buf = cv2.imencode(".png", binary)
    return buf.tobytes() if success else image_bytes


def _deskew(gray: "np.ndarray") -> "np.ndarray":
    """Correct image rotation up to ±45°."""
    try:
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, 3.14159 / 180, 100)

        if lines is None or len(lines) == 0:
            return gray

        angles = []
        for line in lines[:20]:  # sample top 20 lines
            rho, theta = line[0]
            angle = (theta - 3.14159 / 2) * 180 / 3.14159
            if abs(angle) < 45:
                angles.append(angle)

        if not angles:
            return gray

        median_angle = sorted(angles)[len(angles) // 2]
        if abs(median_angle) < 0.5:
            return gray

        h, w = gray.shape
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        rotated = cv2.warpAffine(gray, M, (w, h),
                                  flags=cv2.INTER_CUBIC,
                                  borderMode=cv2.BORDER_REPLICATE)
        return rotated
    except Exception as e:
        logger.debug(f"Deskew failed (non-fatal): {e}")
        return gray


# ── Google Cloud Vision ────────────────────────────────────────
async def ocr_via_vision_api(
    image_bytes: bytes,
    language_hints: list[str] = None,
) -> Optional[OCRResult]:
    """
    Google Cloud Vision API: document_text_detection.
    Handles multilingual handwriting including Devanagari, Tamil, Bengali.
    """
    if not VISION_AVAILABLE:
        return None

    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") and \
       not os.environ.get("GOOGLE_VISION_API_KEY"):
        logger.debug("Google Vision credentials not set — skipping Vision API")
        return None

    try:
        client  = gvision.ImageAnnotatorClient()
        image   = gvision.Image(content=image_bytes)
        context = gvision.ImageContext(
            language_hints=language_hints or ["en", "hi", "mr", "ta", "bn"]
        )
        response = client.document_text_detection(image=image, image_context=context)

        if response.error.message:
            logger.warning(f"Vision API error: {response.error.message}")
            return None

        full_text = response.full_text_annotation.text
        if not full_text.strip():
            return None

        # Compute mean confidence from pages
        confidences = []
        for page in response.full_text_annotation.pages:
            for block in page.blocks:
                confidences.append(block.confidence)

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.7

        return OCRResult(
            text=full_text.strip(),
            confidence=avg_conf,
            language_hints=[l for l in (language_hints or [])],
            engine_used="vision",
            raw_response={"page_count": len(response.full_text_annotation.pages)},
        )
    except Exception as e:
        logger.error(f"Vision API call failed: {e}")
        return None


# ── Tesseract fallback ─────────────────────────────────────────
def ocr_via_tesseract(
    image_bytes: bytes,
    language_hints: list[str] = None,
) -> Optional[OCRResult]:
    """
    Tesseract OCR — self-hosted fallback.
    Language codes: hin (Hindi), mar (Marathi), tam (Tamil), ben (Bengali), eng (English).
    """
    if not TESSERACT_AVAILABLE:
        return None

    try:
        lang_map = {"hi": "hin", "mr": "mar", "ta": "tam", "bn": "ben", "en": "eng"}
        hints    = language_hints or ["en", "hi"]
        tess_langs = "+".join(lang_map.get(h, "eng") for h in hints)

        img = PILImage.open(io.BytesIO(image_bytes))

        # Get text with confidence data
        data = pytesseract.image_to_data(
            img,
            lang=tess_langs,
            output_type=pytesseract.Output.DICT,
        )

        words  = [w for w, c in zip(data["text"], data["conf"]) if int(c) > 0 and w.strip()]
        confs  = [int(c) for c in data["conf"] if int(c) > 0]
        text   = " ".join(words)
        avg_c  = (sum(confs) / len(confs) / 100.0) if confs else 0.0

        if not text.strip():
            return None

        return OCRResult(
            text=text.strip(),
            confidence=avg_c,
            language_hints=hints,
            engine_used="tesseract",
        )
    except Exception as e:
        logger.error(f"Tesseract OCR failed: {e}")
        return None


# ── Main OCR entry point ───────────────────────────────────────
async def extract_text_from_image(
    image_bytes: bytes,
    language_hints: list[str] = None,
    skip_preprocessing: bool = False,
) -> OCRResult:
    """
    Full OCR pipeline:
    1. Preprocess (OpenCV)
    2. Try Google Vision API
    3. Fallback to Tesseract if Vision fails or low confidence
    4. If both fail: return empty result with confidence=0
    """
    if not skip_preprocessing:
        processed = preprocess_image(image_bytes)
    else:
        processed = image_bytes

    # Try Vision API first
    vision_result = await ocr_via_vision_api(processed, language_hints)

    if vision_result and vision_result.confidence >= 0.6:
        logger.info(f"Vision API OCR: conf={vision_result.confidence:.2f}, "
                    f"len={len(vision_result.text)}")
        return vision_result

    # Fallback: Tesseract
    tess_result = ocr_via_tesseract(processed, language_hints)

    if tess_result:
        logger.info(f"Tesseract OCR: conf={tess_result.confidence:.2f}, "
                    f"len={len(tess_result.text)}")
        # If both ran, return whichever has higher confidence
        if vision_result and vision_result.confidence > tess_result.confidence:
            return vision_result
        return tess_result

    # Both failed
    logger.warning("Both OCR engines failed — returning empty result")
    return OCRResult(
        text="",
        confidence=0.0,
        language_hints=language_hints or [],
        engine_used="none",
    )


def extract_text_from_audio_transcript(transcript: str) -> OCRResult:
    """Wrap a Google Speech-to-Text transcript in an OCRResult."""
    return OCRResult(
        text=transcript,
        confidence=0.85,
        language_hints=[],
        engine_used="speech_to_text",
    )
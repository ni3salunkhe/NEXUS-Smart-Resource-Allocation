"""
Notification Service
Channel waterfall: push → WhatsApp → SMS
Two-way SMS: parses volunteer responses (ACCEPT/1, DECLINE/2)
Templates: multilingual task briefing messages
"""
import logging
import os
from dataclasses import dataclass
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    logger.warning("twilio not installed — SMS disabled")

# ── Task briefing templates ───────────────────────────────────
BRIEFING_TEMPLATES: dict[str, dict[str, str]] = {
    "en": {
        "dispatch": (
            "🔔 NEXUS Task Alert\n"
            "Category: {category}\n"
            "Location: {location}\n"
            "Beneficiaries: {beneficiary_count}\n"
            "Description: {description}\n\n"
            "Reply 1 to ACCEPT, 2 to DECLINE\n"
            "Or open the NEXUS app for details."
        ),
        "accepted": "✅ Task accepted. Safe travels to {location}.",
        "reminder": "⏰ Reminder: You have an active task in {location}.",
        "completed": "🙏 Thank you for completing the task. Your work matters.",
    },
    "hi": {
        "dispatch": (
            "🔔 NEXUS कार्य सूचना\n"
            "श्रेणी: {category}\n"
            "स्थान: {location}\n"
            "लाभार्थी: {beneficiary_count}\n"
            "विवरण: {description}\n\n"
            "स्वीकार करने के लिए 1 दबाएं, अस्वीकार के लिए 2"
        ),
        "accepted": "✅ कार्य स्वीकृत। {location} के लिए प्रस्थान करें।",
        "reminder": "⏰ स्मरण: {location} में एक कार्य प्रतीक्षा में है।",
        "completed": "🙏 कार्य पूर्ण करने के लिए धन्यवाद।",
    },
    "mr": {
        "dispatch": (
            "🔔 NEXUS कार्य सूचना\n"
            "श्रेणी: {category}\n"
            "ठिकाण: {location}\n"
            "लाभार्थी: {beneficiary_count}\n"
            "वर्णन: {description}\n\n"
            "स्वीकारण्यासाठी 1, नाकारण्यासाठी 2"
        ),
        "accepted": "✅ कार्य स्वीकारले. {location} ला जा.",
        "reminder": "⏰ स्मरणपत्र: {location} मध्ये कार्य प्रतीक्षेत आहे.",
        "completed": "🙏 कार्य पूर्ण केल्याबद्दल धन्यवाद.",
    },
    "ta": {
        "dispatch": (
            "🔔 NEXUS பணி அறிவிப்பு\n"
            "வகை: {category}\n"
            "இடம்: {location}\n"
            "பயனாளிகள்: {beneficiary_count}\n"
            "விவரம்: {description}\n\n"
            "ஏற்க 1, மறுக்க 2 அழுத்துங்கள்"
        ),
        "accepted": "✅ பணி ஏற்கப்பட்டது. {location} க்கு செல்லுங்கள்.",
        "reminder": "⏰ நினைவூட்டல்: {location} இல் பணி உள்ளது.",
        "completed": "🙏 பணியை முடித்தற்கு நன்றி.",
    },
}


@dataclass
class NotificationResult:
    sent:       bool
    channel:    str
    external_id:Optional[str]
    error:      Optional[str]


def _build_message(
    template_key: str,
    language: str,
    variables: dict,
) -> str:
    lang_templates = BRIEFING_TEMPLATES.get(language, BRIEFING_TEMPLATES["en"])
    template       = lang_templates.get(template_key, BRIEFING_TEMPLATES["en"].get(template_key, ""))
    try:
        return template.format(**variables)
    except KeyError as e:
        logger.warning(f"Template variable missing: {e}")
        return template


# ── Channel implementations ───────────────────────────────────
async def _send_push(push_token: str, message: str, data: dict) -> NotificationResult:
    """Firebase Cloud Messaging stub. In prod: use firebase-admin SDK."""
    if not push_token:
        return NotificationResult(False, "push", None, "no_push_token")
    # Stub: log and return success in dev
    logger.info(f"[PUSH STUB] token={push_token[:12]}... msg={message[:60]}")
    return NotificationResult(True, "push", f"push_{push_token[:8]}", None)


async def _send_whatsapp(
    to_number: str, message: str
) -> NotificationResult:
    """Twilio WhatsApp Business API."""
    sid   = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_wa = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    if not sid or not token or not TWILIO_AVAILABLE:
        logger.info(f"[WHATSAPP STUB] to={to_number} msg={message[:60]}")
        return NotificationResult(True, "whatsapp", f"wa_stub_{to_number[-4:]}", None)

    try:
        client = TwilioClient(sid, token)
        msg    = client.messages.create(
            body=message,
            from_=from_wa,
            to=f"whatsapp:{to_number}",
        )
        return NotificationResult(True, "whatsapp", msg.sid, None)
    except Exception as e:
        logger.error(f"WhatsApp send failed: {e}")
        return NotificationResult(False, "whatsapp", None, str(e))


async def _send_sms(to_number: str, message: str) -> NotificationResult:
    """Twilio SMS — universal fallback."""
    sid   = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_sms = os.environ.get("TWILIO_SMS_FROM", "+14155238886")

    if not sid or not token or not TWILIO_AVAILABLE:
        logger.info(f"[SMS STUB] to={to_number} msg={message[:80]}")
        return NotificationResult(True, "sms", f"sms_stub_{to_number[-4:]}", None)

    try:
        client = TwilioClient(sid, token)
        msg    = client.messages.create(body=message, from_=from_sms, to=to_number)
        return NotificationResult(True, "sms", msg.sid, None)
    except Exception as e:
        logger.error(f"SMS send failed: {e}")
        return NotificationResult(False, "sms", None, str(e))


# ── Waterfall dispatcher ──────────────────────────────────────
async def dispatch_notification(
    db: AsyncSession,
    task_id: str,
    volunteer_id: str,
    tenant_id: str,
    template_key: str,
    language: str,
    variables: dict,
    push_token: Optional[str]     = None,
    whatsapp_number: Optional[str]= None,
    phone_number: Optional[str]   = None,
    preferred_channel: str        = "push",
) -> NotificationResult:
    """
    Waterfall: preferred_channel → whatsapp → sms.
    Persists result to notifications table.
    """
    message = _build_message(template_key, language, variables)

    result: Optional[NotificationResult] = None

    # Try push first if preferred or available
    if preferred_channel == "push" and push_token:
        result = await _send_push(push_token, message, {"task_id": task_id})

    # Try WhatsApp
    if (not result or not result.sent) and whatsapp_number:
        result = await _send_whatsapp(whatsapp_number, message)

    # SMS fallback
    if (not result or not result.sent) and phone_number:
        result = await _send_sms(phone_number, message)

    if not result:
        result = NotificationResult(False, "none", None, "no_channel_available")

    # Persist to notifications table
    await db.execute(
        text("""
            INSERT INTO notifications
                (tenant_id, task_id, volunteer_id, channel,
                 template_key, message_body, language,
                 status, sent_at, external_id, error_detail)
            VALUES
                (:tid, :task_id, :vol_id, :channel,
                 :tkey, :body, :lang,
                 :status, CASE WHEN :sent THEN NOW() END,
                 :ext_id, :err)
        """),
        {
            "tid":     tenant_id,
            "task_id": task_id,
            "vol_id":  volunteer_id,
            "channel": result.channel,
            "tkey":    template_key,
            "body":    message,
            "lang":    language,
            "status":  "sent" if result.sent else "failed",
            "sent":    result.sent,
            "ext_id":  result.external_id,
            "err":     result.error,
        }
    )

    return result


# ── Two-way SMS parsing ───────────────────────────────────────
def parse_sms_response(body: str) -> tuple[str, str]:
    """
    Parse inbound SMS from volunteer.
    Returns (action, reason) where action ∈ "accept" | "decline" | "unknown".
    """
    body = body.strip().lower()
    if body in ("1", "yes", "accept", "ok", "haan", "ha"):
        return "accept", ""
    if body.startswith("2") or body in ("no", "decline", "nahi", "na", "busy"):
        # Extract optional reason after "2 " or "decline "
        parts  = body.split(" ", 1)
        reason = parts[1] if len(parts) > 1 else ""
        return "decline", reason
    return "unknown", body


async def handle_whatsapp_webhook(
    db: AsyncSession,
    from_number: str,
    body: str,
    tenant_id: str,
) -> dict:
    """
    Process inbound WhatsApp/SMS reply from a volunteer.
    Looks up the most recent dispatched task for this volunteer's number.
    """
    # Find volunteer by phone number
    vol_result = await db.execute(
        text("""
            SELECT volunteer_id FROM volunteers
            WHERE (whatsapp_number = :num OR phone_number = :num)
              AND tenant_id = :tid
              AND active = TRUE
            LIMIT 1
        """),
        {"num": from_number, "tid": tenant_id}
    )
    vol_row = vol_result.fetchone()
    if not vol_row:
        return {"status": "volunteer_not_found"}

    volunteer_id = str(vol_row.volunteer_id)

    # Find most recent dispatched task for this volunteer
    task_result = await db.execute(
        text("""
            SELECT task_id FROM tasks
            WHERE assigned_volunteer_id = :vid
              AND tenant_id             = :tid
              AND status                = 'dispatched'
            ORDER BY dispatched_at DESC
            LIMIT 1
        """),
        {"vid": volunteer_id, "tid": tenant_id}
    )
    task_row = task_result.fetchone()
    if not task_row:
        return {"status": "no_dispatched_task"}

    task_id = str(task_row.task_id)
    action, reason = parse_sms_response(body)

    return {
        "volunteer_id": volunteer_id,
        "task_id":      task_id,
        "action":       action,
        "reason":       reason,
    }
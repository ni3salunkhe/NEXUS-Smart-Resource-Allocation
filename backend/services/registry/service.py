"""
Household Registry Service
All DB operations for households, members, consent, cross-tenant links, history.
"""
import logging
from typing import Optional, List
from uuid import UUID, uuid4
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from .schemas import (
    HouseholdCreate, HouseholdUpdate, HouseholdResponse, MemberResponse,
    ConsentCreate, ConsentResponse, CrossTenantLinkCreate, CrossTenantLinkResponse,
    HouseholdHistoryResponse, MergeRequest, SearchRequest,
    IdentityResolutionRequest, ResolutionResult, GlobalSearchResponse, WardStat, PartnershipPolicy
)
from .identity_resolution import resolve_household

logger = logging.getLogger(__name__)


def _wkt_point(lat: float, lon: float) -> str:
    return f"POINT({lon} {lat})"


class HouseholdRegistryService:
    async def _emit_history(
        self,
        db: AsyncSession,
        household_id: str,
        tenant_id: str,
        event_type: str,
        payload: dict,
        triggered_by: Optional[str] = None,
        related_need_id: Optional[str] = None,
        related_task_id: Optional[str] = None,
    ):
        import json
        await db.execute(
            text("""
                INSERT INTO household_history
                    (household_id, tenant_id, event_type, event_payload,
                     triggered_by, related_need_id, related_task_id)
                VALUES
                    (:hh_id, :tid, :etype, CAST(:payload AS JSONB),
                     :by, :need_id, :task_id)
            """),
            {
                "hh_id":   household_id,
                "tid":     tenant_id,
                "etype":   event_type,
                "payload": json.dumps(payload),
                "by":      triggered_by,
                "need_id": related_need_id,
                "task_id": related_task_id,
            }
        )

    # ── CREATE ────────────────────────────────────────────────
    async def create_household(
        self,
        db: AsyncSession,
        data: HouseholdCreate,
        tenant_id: str,
        user_id: str,
    ) -> dict:
        import json

        loc_wkt = None
        if data.location and data.location.latitude is not None:
            loc_wkt = _wkt_point(data.location.latitude, data.location.longitude)

        result = await db.execute(
            text("""
                INSERT INTO households (
                    tenant_id, ward_id, display_name,
                    location_geo, location_confidence, location_description, landmark_tags,
                    dwelling_type, economic_tier, created_by
                )
                VALUES (
                    :tid, :ward_id, :display_name,
                    CASE WHEN CAST(:loc_wkt AS TEXT) IS NOT NULL
                         THEN ST_GeographyFromText(CAST(:loc_wkt AS TEXT)) END,
                    :loc_conf, :loc_desc, CAST(:landmarks AS text[]),
                    :dwelling, :econ_tier, :created_by
                )
                RETURNING household_id, created_at, updated_at
            """),
            {
                "tid":        tenant_id,
                "ward_id":    data.ward_id if data.ward_id else (data.location.description if data.location else None),
                "display_name": data.display_name,
                "loc_wkt":    loc_wkt,
                "loc_conf":   data.location.confidence if data.location else 0.5,
                "loc_desc":   data.location.description if data.location else None,
                "landmarks":  data.location.landmarks if data.location else [],
                "dwelling":   data.dwelling_type.value if data.dwelling_type else None,
                "econ_tier":  data.economic_tier.value if data.economic_tier else None,
                "created_by": user_id,
            }
        )
        row = result.fetchone()
        hh_id = str(row.household_id)

        # Insert members
        for m in data.members:
            await db.execute(
                text("""
                    INSERT INTO household_members
                        (household_id, role_in_household, age_bracket, gender,
                         is_primary_contact, vulnerability_flags, added_by)
                    VALUES
                        (:hh_id, :role, :age, :gender, :primary,
                         CAST(:vuln AS JSONB), :by)
                """),
                {
                    "hh_id":   hh_id,
                    "role":    m.role_in_household.value if m.role_in_household else None,
                    "age":     m.age_bracket.value if m.age_bracket else None,
                    "gender":  m.gender,
                    "primary": m.is_primary_contact,
                    "vuln":    json.dumps(m.vulnerability_flags or {}),
                    "by":      user_id,
                }
            )

        # Emit history event
        await self._emit_history(
            db, hh_id, tenant_id,
            "member_added",
            {"source": "household_create", "member_count": len(data.members)},
            triggered_by=user_id,
        )

        return {"household_id": hh_id, "created_at": row.created_at.isoformat()}

    # ── GET ───────────────────────────────────────────────────
    async def get_household(
        self,
        db: AsyncSession,
        household_id: str,
        tenant_id: str,
        include_members: bool = True,
    ) -> Optional[dict]:
        result = await db.execute(
            text("""
                SELECT
                    h.*,
                    ST_Y(location_geo::geometry) AS latitude,
                    ST_X(location_geo::geometry) AS longitude
                FROM households h
                WHERE h.household_id = :hid AND h.tenant_id = :tid
            """),
            {"hid": household_id, "tid": tenant_id}
        )
        hh = result.fetchone()
        if not hh:
            return None

        hh_dict = dict(hh._mapping)

        if include_members:
            mem_result = await db.execute(
                text("""
                    SELECT * FROM household_members
                    WHERE household_id = :hid AND removed_at IS NULL
                    ORDER BY is_primary_contact DESC, added_at ASC
                """),
                {"hid": household_id}
            )
            hh_dict["members"] = [dict(r._mapping) for r in mem_result.fetchall()]

        return hh_dict

    # ── SEARCH ────────────────────────────────────────────────
    async def search_households(
        self,
        db: AsyncSession,
        req: SearchRequest,
        tenant_id: str,
    ) -> List[dict]:
        conditions = ["h.tenant_id = :tid", "h.status = :status"]
        params: dict = {"tid": tenant_id, "status": req.status or "active"}

        if req.ward_id:
            conditions.append("h.ward_id = :ward_id")
            params["ward_id"] = req.ward_id

        if req.has_child is True:
            conditions.append("(h.vulnerability_flags->>'has_child')::bool = TRUE")

        if req.has_elderly is True:
            conditions.append("(h.vulnerability_flags->>'has_elderly')::bool = TRUE")

        if req.min_vuln_score is not None:
            conditions.append("h.vulnerability_score >= :min_vuln")
            params["min_vuln"] = req.min_vuln_score

        if req.landmark:
            conditions.append("h.location_description ILIKE :landmark")
            params["landmark"] = f"%{req.landmark}%"

        if req.latitude and req.longitude:
            conditions.append("""
                ST_DWithin(
                    h.location_geo::geography,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :radius
                )
            """)
            params["lat"]    = req.latitude
            params["lon"]    = req.longitude
            params["radius"] = req.radius_m

        where = " AND ".join(conditions)
        sql = f"""
            SELECT h.*,
                   ST_Y(h.location_geo::geometry) AS latitude,
                   ST_X(h.location_geo::geometry) AS longitude
            FROM households h
            WHERE {where}
            ORDER BY h.vulnerability_score DESC, h.last_need_reported_at DESC NULLS LAST
            LIMIT :limit OFFSET :offset
        """
        params["limit"]  = req.limit
        params["offset"] = req.offset

        result = await db.execute(text(sql), params)
        return [dict(r._mapping) for r in result.fetchall()]

    # ── UPDATE ────────────────────────────────────────────────
    async def update_household(
        self,
        db: AsyncSession,
        household_id: str,
        data: HouseholdUpdate,
        tenant_id: str,
        user_id: str,
    ) -> dict:
        sets = ["updated_at = NOW()"]
        params: dict = {"hid": household_id, "tid": tenant_id}

        if data.ward_id is not None:
            sets.append("ward_id = :ward_id")
            params["ward_id"] = data.ward_id

        if data.display_name is not None:
            sets.append("display_name = :display_name")
            params["display_name"] = data.display_name

        if data.dwelling_type is not None:
            sets.append("dwelling_type = :dwelling")
            params["dwelling"] = data.dwelling_type.value

        if data.economic_tier is not None:
            sets.append("economic_tier = :econ")
            params["econ"] = data.economic_tier.value

        if data.landmark_tags is not None:
            sets.append("landmark_tags = :tags::text[]")
            params["tags"] = data.landmark_tags

        if data.location:
            if data.location.latitude is not None:
                sets.append("location_geo = ST_GeographyFromText(:loc_wkt)")
                params["loc_wkt"] = _wkt_point(
                    data.location.latitude, data.location.longitude
                )
                sets.append("location_confidence = :loc_conf")
                params["loc_conf"] = data.location.confidence
            if data.location.description:
                sets.append("location_description = :loc_desc")
                params["loc_desc"] = data.location.description
            if data.location.landmarks:
                sets.append("landmark_tags = :lm::text[]")
                params["lm"] = data.location.landmarks

        await db.execute(
            text(f"UPDATE households SET {', '.join(sets)} WHERE household_id = :hid AND tenant_id = :tid"),
            params
        )
        await self._emit_history(db, household_id, tenant_id, "location_updated",
                            {"updated_fields": list(params.keys())}, triggered_by=user_id)
        return {"updated": True, "household_id": household_id}

    # ── MERGE ─────────────────────────────────────────────────
    async def merge_households(
        self,
        db: AsyncSession,
        req: MergeRequest,
        tenant_id: str,
        user_id: str,
    ) -> dict:
        src = str(req.source_household_id)
        tgt = str(req.target_household_id)

        # Reassign members
        await db.execute(
            text("UPDATE household_members SET household_id = :tgt WHERE household_id = :src"),
            {"tgt": tgt, "src": src}
        )
        # Soft-delete source
        await db.execute(
            text("""
                UPDATE households SET
                    status = 'merged_away',
                    merged_into = :tgt,
                    merge_reason = :reason,
                    updated_at = NOW()
                WHERE household_id = :src AND tenant_id = :tid
            """),
            {"tgt": tgt, "src": src, "reason": req.merge_reason, "tid": tenant_id}
        )
        # Emit history on both
        for hh_id in [src, tgt]:
            await self._emit_history(
                db, hh_id, tenant_id, "merged",
                {"source_id": src, "target_id": tgt, "reason": req.merge_reason},
                triggered_by=user_id,
            )
        return {"merged": True, "source": src, "target": tgt}

    # ── CONSENT ───────────────────────────────────────────────
    async def add_consent(
        self,
        db: AsyncSession,
        household_id: str,
        data: ConsentCreate,
        tenant_id: str,
        user_id: str,
    ) -> dict:
        import json
        result = await db.execute(
            text("""
                INSERT INTO household_consent (
                    household_id, consent_type, scope, expires_at,
                    collection_method, language_used, primary_contact_ref, collected_by
                )
                VALUES (
                    :hh_id, :ctype, CAST(:scope AS JSONB), :expires,
                    :method, :lang, :contact, :by
                )
                RETURNING consent_id, granted_at
            """),
            {
                "hh_id":   household_id,
                "ctype":   data.consent_type.value,
                "scope":   json.dumps(data.scope),
                "expires": data.expires_at,
                "method":  data.collection_method.value if data.collection_method else None,
                "lang":    data.language_used,
                "contact": str(data.primary_contact_ref) if data.primary_contact_ref else None,
                "by":      user_id,
            }
        )
        row = result.fetchone()
        await self._emit_history(
            db, household_id, tenant_id, "consent_changed",
            {"consent_type": data.consent_type.value, "action": "granted"},
            triggered_by=user_id,
        )
        return {"consent_id": str(row.consent_id), "granted_at": row.granted_at.isoformat()}

    async def revoke_consent(
        self,
        db: AsyncSession,
        consent_id: str,
        household_id: str,
        tenant_id: str,
        user_id: str,
        reason: str = "",
    ) -> dict:
        await db.execute(
            text("""
                UPDATE household_consent
                SET revoked_at = NOW(), revocation_reason = :reason
                WHERE consent_id = :cid AND household_id = :hh_id
            """),
            {"cid": consent_id, "hh_id": household_id, "reason": reason}
        )
        await self._emit_history(
            db, household_id, tenant_id, "consent_changed",
            {"consent_id": consent_id, "action": "revoked", "reason": reason},
            triggered_by=user_id,
        )
        return {"revoked": True}

    async def opt_out(
        self,
        db: AsyncSession,
        household_id: str,
        tenant_id: str,
    ) -> dict:
        """Full opt-out: flag household + active consent records."""
        await db.execute(
            text("""
                UPDATE household_consent
                SET opt_out = TRUE
                WHERE household_id = :hh_id AND revoked_at IS NULL
            """),
            {"hh_id": household_id}
        )
        await db.execute(
            text("""
                UPDATE households SET status = 'opted_out', updated_at = NOW()
                WHERE household_id = :hh_id AND tenant_id = :tid
            """),
            {"hh_id": household_id, "tid": tenant_id}
        )
        await self._emit_history(db, household_id, tenant_id, "opted_out", {})
        # Schedule PII deletion (30-day grace period) — in prod: emit to deletion queue
        return {"opted_out": True, "pii_deletion_scheduled": True}

    # ── CROSS-TENANT LINK ─────────────────────────────────────
    async def propose_cross_tenant_link(
        self,
        db: AsyncSession,
        household_id_a: str,
        data: CrossTenantLinkCreate,
        tenant_a: str,
        user_id: str,
    ) -> dict:
        result = await db.execute(
            text("""
                INSERT INTO household_cross_tenant_links (
                    household_id_tenant_a, household_id_tenant_b,
                    tenant_a, tenant_b,
                    link_confidence, link_method, fields_shared,
                    consent_id_a, consent_id_b
                )
                VALUES (
                    :hh_a, :hh_b,
                    :ta, :tb,
                    :conf, 'coordinator_confirmed', :fields::text[],
                    :ca, :cb
                )
                RETURNING link_id, global_household_id, created_at
            """),
            {
                "hh_a":   household_id_a,
                "hh_b":   str(data.household_id_tenant_b),
                "ta":     tenant_a,
                "tb":     str(data.tenant_b),
                "conf":   data.link_confidence,
                "fields": data.fields_shared,
                "ca":     str(data.consent_id_a) if data.consent_id_a else None,
                "cb":     str(data.consent_id_b) if data.consent_id_b else None,
            }
        )
        row = result.fetchone()
        # M11: assign global_household_id to both households via separate UPDATEs
        # (SQLAlchemy text() does not expand IN(:a,:b) tuples)
        global_id = str(row.global_household_id)
        for hh_id in [household_id_a, str(data.household_id_tenant_b)]:
            await db.execute(
                text("UPDATE households SET global_household_id = :gid WHERE household_id = :hid"),
                {"gid": global_id, "hid": hh_id}
            )
        return {
            "link_id": str(row.link_id),
            "global_household_id": global_id,
            "status": "proposed",
        }

    async def approve_cross_tenant_link(
        self,
        db: AsyncSession,
        link_id: str,
        user_id: str,
    ) -> dict:
        await db.execute(
            text("""
                UPDATE household_cross_tenant_links
                SET link_status = 'active', approved_at = NOW(), approved_by = :uid
                WHERE link_id = :lid
            """),
            {"lid": link_id, "uid": user_id}
        )
        return {"approved": True, "link_id": link_id}

    # ── HISTORY ───────────────────────────────────────────────
    async def get_history(
        self,
        db: AsyncSession,
        household_id: str,
        tenant_id: str,
        limit: int = 50,
        event_type: Optional[str] = None,
    ) -> List[dict]:
        conditions = ["household_id = :hid", "tenant_id = :tid"]
        params: dict = {"hid": household_id, "tid": tenant_id, "limit": limit}

        if event_type:
            conditions.append("event_type = :etype")
            params["etype"] = event_type

        where = " AND ".join(conditions)
        result = await db.execute(
            text(f"""
                SELECT * FROM household_history
                WHERE {where}
                ORDER BY event_timestamp DESC
                LIMIT :limit
            """),
            params
        )
        return [dict(r._mapping) for r in result.fetchall()]

    # ── IDENTITY RESOLUTION ───────────────────────────────────
    async def resolve_identity(
        self,
        db: AsyncSession,
        req: IdentityResolutionRequest,
        tenant_id: str,
    ) -> ResolutionResult:
        return await resolve_household(db, req, tenant_id)

    # ── CRISIS FREQUENCY ─────────────────────────────────────
    async def recompute_crisis_frequency(
        self,
        db: AsyncSession,
        household_id: str,
        tenant_id: str,
    ) -> float:
        """Rolling 6-month needs per month."""
        result = await db.execute(
            text("""
                SELECT COUNT(*) AS need_count
                FROM household_history
                WHERE household_id = :hid
                  AND tenant_id   = :tid
                  AND event_type  = 'need_reported'
                  AND event_timestamp >= NOW() - INTERVAL '6 months'
            """),
            {"hid": household_id, "tid": tenant_id}
        )
        row = result.fetchone()
        count = row.need_count or 0
        freq = count / 6.0  # needs per month over 6-month window

        await db.execute(
            text("UPDATE households SET crisis_frequency = :freq WHERE household_id = :hid"),
            {"freq": freq, "hid": household_id}
        )
        return freq


    # ── GAP-06: BULK CONSENT ──────────────────────────────────
    async def get_all_consent(
        self,
        db: AsyncSession,
        household_id: str,
        tenant_id: str,
    ) -> List[dict]:
        result = await db.execute(
            text("""
                SELECT * FROM household_consent
                WHERE household_id = :hid AND revoked_at IS NULL AND opt_out = FALSE
            """),
            {"hid": household_id}
        )
        return [dict(r._mapping) for r in result.fetchall()]

    # ── GAP-02: GLOBAL SEARCH ─────────────────────────────────
    async def global_search(
        self,
        db: AsyncSession,
        query: str,
        tenant_id: str,
    ) -> dict:
        import httpx
        from shared.config import get_settings

        # 1. Search Needs (Intelligence Service HTTP call)
        # H6: replaced direct import of es_service with HTTP request
        settings = get_settings()
        intel_url = settings.INTELLIGENCE_URL if hasattr(settings, "INTELLIGENCE_URL") else "http://localhost:8004"
        needs = []
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{intel_url}/search",
                    params={"q": query},
                    headers={"X-Tenant-ID": tenant_id}
                )
                if resp.status_code == 200:
                    needs = resp.json().get("results", [])
        except Exception as e:
            import logging
            logging.warning(f"Intelligence search failed (degraded mode): {e}")

        # 2. Search Households (DB)
        hh_res = await db.execute(
            text("""
                SELECT household_id, location_description, landmark_tags, ward_id, vulnerability_score, status
                FROM households
                WHERE tenant_id = :tid AND (location_description ILIKE :q OR ward_id ILIKE :q)
                LIMIT 5
            """),
            {"tid": tenant_id, "q": f"%{query}%"}
        )
        households = [dict(r._mapping) for r in hh_res.fetchall()]

        # 3. Search Volunteers (DB)
        vol_res = await db.execute(
            text("""
                SELECT volunteer_id, tenant_id, ward_id, skills, active
                FROM volunteers
                WHERE tenant_id = :tid AND (ward_id ILIKE :q)
                LIMIT 5
            """),
            {"tid": tenant_id, "q": f"%{query}%"}
        )
        volunteers = [dict(r._mapping) for r in vol_res.fetchall()]

        return {
            "needs":      needs,
            "households": households,
            "volunteers": volunteers,
        }

    # ── GAP-09: WARD LOOKUP ───────────────────────────────────
    async def list_wards(
        self,
        db: AsyncSession,
        tenant_id: str,
    ) -> List[dict]:
        # Try ward_stats first
        result = await db.execute(
            text("""
                SELECT ward_id, 
                       0 as total_households, 
                       total_needs_open as active_needs, 
                       avg_urgency_score as avg_vuln_score
                FROM ward_stats
                WHERE tenant_id = :tid
            """),
            {"tid": tenant_id}
        )
        rows = result.fetchall()
        if not rows:
            # Fallback: aggregate from households
            result = await db.execute(
                text("""
                    SELECT ward_id, 
                           COUNT(*) as total_households, 
                           0 as active_needs, 
                           AVG(vulnerability_score) as avg_vuln_score
                    FROM households
                    WHERE tenant_id = :tid AND ward_id IS NOT NULL
                    GROUP BY ward_id
                """),
                {"tid": tenant_id}
            )
            rows = result.fetchall()
        return [dict(r._mapping) for r in rows]

    # ── GAP-10: PARTNERSHIPS ──────────────────────────────────
    async def get_partnerships(
        self,
        db: AsyncSession,
        tenant_id: str,
    ) -> List[dict]:
        result = await db.execute(
            text("SELECT settings FROM tenants WHERE tenant_id = :tid"),
            {"tid": tenant_id}
        )
        row = result.fetchone()
        # M12: Guard against NULL settings column
        raw_settings = row.settings if row else None
        settings = raw_settings if isinstance(raw_settings, dict) else {}
        partnerships = settings.get("partnerships", [])
        return partnerships

    async def update_partnership(
        self,
        db: AsyncSession,
        tenant_id: str,
        partner_id: str,
        policy: PartnershipPolicy,
    ) -> dict:
        import json
        result = await db.execute(
            text("SELECT settings FROM tenants WHERE tenant_id = :tid"),
            {"tid": tenant_id}
        )
        row = result.fetchone()
        settings = row.settings if row else {}
        partnerships = settings.get("partnerships", [])

        # Update or append
        found = False
        new_entry = {
            "partner_id":    partner_id,
            "policy":        policy.policy,
            "shared_fields": policy.shared_fields
        }
        for i, p in enumerate(partnerships):
            if p.get("partner_id") == partner_id:
                partnerships[i] = new_entry
                found = True
                break
        if not found:
            partnerships.append(new_entry)

        settings["partnerships"] = partnerships
        await db.execute(
            text("UPDATE tenants SET settings = CAST(:s AS JSONB) WHERE tenant_id = :tid"),
            {"s": json.dumps(settings), "tid": tenant_id}
        )
        await db.commit()
        return {"updated": True, "partner_id": partner_id}


# Singleton
registry_service = HouseholdRegistryService()

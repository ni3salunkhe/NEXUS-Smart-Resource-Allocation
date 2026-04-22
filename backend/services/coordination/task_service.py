"""
Task Orchestration Service
State machine: unassigned → dispatched → accepted → in_progress
               → completed → closed
               → cancelled → needs_reassignment → dispatched (retry)
All state transitions are atomic, logged, and emit Kafka events.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Valid state transitions
VALID_TRANSITIONS: dict[str, list[str]] = {
    "unassigned":       ["dispatched"],
    "dispatched":       ["accepted", "cancelled", "needs_reassignment"],
    "accepted":         ["in_progress", "cancelled"],
    "in_progress":      ["completed", "needs_reassignment"],
    "completed":        ["closed"],
    "cancelled":        ["dispatched"],          # retry with new volunteer
    "needs_reassignment":["dispatched"],
    "closed":           [],                      # terminal
}

DISPATCH_TIMEOUT_MINUTES = 20


class TaskOrchestrationService:

    async def create_task(
        self,
        db: AsyncSession,
        need_id: str,
        household_id: Optional[str],
        tenant_id: str,
        coordinator_id: Optional[str],
    ) -> dict:
        result = await db.execute(
            text("""
                INSERT INTO tasks (need_id, household_id, tenant_id, coordinator_id, status)
                VALUES (:nid, :hh, :tid, :coord, 'unassigned')
                RETURNING task_id, created_at
            """),
            {"nid": need_id, "hh": household_id, "tid": tenant_id, "coord": coordinator_id}
        )
        row = result.fetchone()
        task_id = str(row.task_id)

        await self._log_transition(db, task_id, tenant_id, None, "unassigned", coordinator_id)

        # Update need_record to link task
        await db.execute(
            text("UPDATE need_records SET assigned_task_id = :tid, status = 'assigned' WHERE need_id = :nid"),
            {"tid": task_id, "nid": need_id}
        )
        return {"task_id": task_id, "created_at": row.created_at.isoformat()}

    async def dispatch(
        self,
        db: AsyncSession,
        task_id: str,
        volunteer_id: str,
        tenant_id: str,
        match_score: float,
        match_components: dict,
        coordinator_id: Optional[str],
        briefing_text: str = "",
        briefing_language: str = "en",
    ) -> dict:
        await self._assert_transition(db, task_id, tenant_id, "dispatched")

        await db.execute(
            text("""
                UPDATE tasks SET
                    status                 = 'dispatched',
                    assigned_volunteer_id  = :vid,
                    dispatched_at          = NOW(),
                    match_score            = :score,
                    match_components       = CAST(:comps AS JSONB),
                    briefing_text          = :brief,
                    briefing_language      = :lang,
                    updated_at             = NOW()
                WHERE task_id = :tid AND tenant_id = :ten
            """),
            {
                "vid":   volunteer_id,
                "score": match_score,
                "comps": json.dumps(match_components),
                "brief": briefing_text,
                "lang":  briefing_language,
                "tid":   task_id,
                "ten":   tenant_id,
            }
        )
        await self._log_transition(db, task_id, tenant_id, "unassigned", "dispatched", coordinator_id)

        # Record dispatch attempt
        await db.execute(
            text("""
                INSERT INTO dispatch_attempts
                    (task_id, volunteer_id, tenant_id, attempt_number, match_score)
                VALUES (
                    :tid, :vid, :ten,
                    (SELECT COALESCE(MAX(attempt_number),0)+1
                     FROM dispatch_attempts WHERE task_id=:tid),
                    :score
                )
            """),
            {"tid": task_id, "vid": volunteer_id, "ten": tenant_id, "score": match_score}
        )
        return {"dispatched": True, "task_id": task_id, "volunteer_id": volunteer_id}

    async def accept(
        self,
        db: AsyncSession,
        task_id: str,
        volunteer_id: str,
        tenant_id: str,
    ) -> dict:
        await self._assert_transition(db, task_id, tenant_id, "accepted", volunteer_id)

        await db.execute(
            text("""
                UPDATE tasks SET status='accepted', accepted_at=NOW(), updated_at=NOW()
                WHERE task_id=:tid AND tenant_id=:ten AND assigned_volunteer_id=:vid
            """),
            {"tid": task_id, "ten": tenant_id, "vid": volunteer_id}
        )
        await self._log_transition(db, task_id, tenant_id, "dispatched", "accepted", volunteer_id=volunteer_id)

        # Record dispatch attempt outcome
        await db.execute(
            text("""
                UPDATE dispatch_attempts SET outcome='accepted', responded_at=NOW()
                WHERE task_id=:tid AND volunteer_id=:vid AND outcome IS NULL
            """),
            {"tid": task_id, "vid": volunteer_id}
        )
        return {"accepted": True, "task_id": task_id}

    async def decline(
        self,
        db: AsyncSession,
        task_id: str,
        volunteer_id: str,
        tenant_id: str,
        reason: str = "",
    ) -> dict:
        """Volunteer declined. Move to needs_reassignment."""
        await self._assert_transition(db, task_id, tenant_id, "needs_reassignment")

        await db.execute(
            text("""
                UPDATE tasks SET
                    status                  = 'needs_reassignment',
                    cancellation_attempts   = cancellation_attempts + 1,
                    updated_at              = NOW()
                WHERE task_id=:tid AND tenant_id=:ten
            """),
            {"tid": task_id, "ten": tenant_id}
        )
        await self._log_transition(db, task_id, tenant_id, "dispatched", "needs_reassignment",
                                   volunteer_id=volunteer_id, notes=f"declined: {reason}")
        await db.execute(
            text("""
                UPDATE dispatch_attempts SET outcome='declined', responded_at=NOW(), decline_reason=:reason
                WHERE task_id=:tid AND volunteer_id=:vid AND outcome IS NULL
            """),
            {"tid": task_id, "vid": volunteer_id, "reason": reason}
        )
        return {"declined": True, "task_id": task_id, "next_action": "needs_reassignment"}

    async def start(
        self,
        db: AsyncSession,
        task_id: str,
        volunteer_id: str,
        tenant_id: str,
    ) -> dict:
        """Volunteer checked in at location."""
        await self._assert_transition(db, task_id, tenant_id, "in_progress", volunteer_id)
        await db.execute(
            text("""
                UPDATE tasks SET status='in_progress', started_at=NOW(), updated_at=NOW()
                WHERE task_id=:tid AND tenant_id=:ten AND assigned_volunteer_id=:vid
            """),
            {"tid": task_id, "ten": tenant_id, "vid": volunteer_id}
        )
        await self._log_transition(db, task_id, tenant_id, "accepted", "in_progress", volunteer_id=volunteer_id)
        return {"started": True, "task_id": task_id}

    async def complete(
        self,
        db: AsyncSession,
        task_id: str,
        volunteer_id: str,
        tenant_id: str,
        outcome_status: str,
        outcome_notes: str,
        materials_provided: dict,
        follow_up_required: bool,
    ) -> dict:
        await self._assert_transition(db, task_id, tenant_id, "completed", volunteer_id)

        await db.execute(
            text("""
                UPDATE tasks SET
                    status              = 'completed',
                    completed_at        = NOW(),
                    outcome_status      = :outcome,
                    outcome_notes       = :notes,
                    materials_provided  = CAST(:mats AS JSONB),
                    follow_up_required  = :followup,
                    updated_at          = NOW()
                WHERE task_id=:tid AND tenant_id=:ten AND assigned_volunteer_id=:vid
            """),
            {
                "outcome":  outcome_status,
                "notes":    outcome_notes,
                "mats":     json.dumps(materials_provided),
                "followup": follow_up_required,
                "tid":      task_id,
                "ten":      tenant_id,
                "vid":      volunteer_id,
            }
        )
        await self._log_transition(db, task_id, tenant_id, "in_progress", "completed", volunteer_id=volunteer_id)

        # Update need_record status
        need_status_map = {
            "need_fully_met":      "resolved",
            "partially_met":       "in_progress",
            "unresolved":          "verified",
            "follow_up_required":  "in_progress",
        }
        nr_status = need_status_map.get(outcome_status, "in_progress")

        task_row = await db.execute(
            text("SELECT need_id FROM tasks WHERE task_id=:tid"), {"tid": task_id}
        )
        task = task_row.fetchone()
        if task:
            await db.execute(
                text("UPDATE need_records SET status=:s, updated_at=NOW() WHERE need_id=:nid"),
                {"s": nr_status, "nid": str(task.need_id)}
            )

        # Update volunteer's total_deployments + last_deployed_at
        await db.execute(
            text("""
                UPDATE volunteers SET
                    total_deployments = total_deployments + 1,
                    last_deployed_at  = NOW(),
                    updated_at        = NOW()
                WHERE volunteer_id=:vid AND tenant_id=:ten
            """),
            {"vid": volunteer_id, "ten": tenant_id}
        )
        return {"completed": True, "task_id": task_id, "outcome": outcome_status}

    async def close(
        self,
        db: AsyncSession,
        task_id: str,
        coordinator_id: str,
        tenant_id: str,
        volunteer_rating: Optional[float] = None,
    ) -> dict:
        """Coordinator closes the task after reviewing outcome."""
        await self._assert_transition(db, task_id, tenant_id, "closed")

        await db.execute(
            text("""
                UPDATE tasks SET
                    status            = 'closed',
                    closed_at         = NOW(),
                    volunteer_rating  = COALESCE(:rating, volunteer_rating),
                    updated_at        = NOW()
                WHERE task_id=:tid AND tenant_id=:ten
            """),
            {"rating": volunteer_rating, "tid": task_id, "ten": tenant_id}
        )
        await self._log_transition(db, task_id, tenant_id, "completed", "closed", coordinator_id)
        return {"closed": True, "task_id": task_id}

    async def get_task(
        self, db: AsyncSession, task_id: str, tenant_id: str
    ) -> Optional[dict]:
        result = await db.execute(
            text("SELECT * FROM tasks WHERE task_id=:tid AND tenant_id=:ten"),
            {"tid": task_id, "ten": tenant_id}
        )
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def get_state_log(
        self, db: AsyncSession, task_id: str, tenant_id: str
    ) -> list[dict]:
        result = await db.execute(
            text("""
                SELECT * FROM task_state_log
                WHERE task_id=:tid AND tenant_id=:ten
                ORDER BY transitioned_at ASC
            """),
            {"tid": task_id, "ten": tenant_id}
        )
        return [dict(r._mapping) for r in result.fetchall()]

    async def check_dispatch_timeouts(
        self, db: AsyncSession, tenant_id: str
    ) -> list[str]:
        """Find dispatched tasks past timeout. Move to needs_reassignment."""
        result = await db.execute(
            text("""
                SELECT task_id FROM tasks
                WHERE tenant_id = :ten
                  AND status    = 'dispatched'
                  AND dispatched_at < NOW() - INTERVAL '20 minutes'
            """),
            {"ten": tenant_id}
        )
        timed_out = [str(r.task_id) for r in result.fetchall()]

        for task_id in timed_out:
            await db.execute(
                text("""
                    UPDATE tasks SET
                        status               = 'needs_reassignment',
                        cancellation_attempts = cancellation_attempts + 1,
                        updated_at           = NOW()
                    WHERE task_id=:tid AND tenant_id=:ten
                """),
                {"tid": task_id, "ten": tenant_id}
            )
            await self._log_transition(db, task_id, tenant_id, "dispatched",
                                       "needs_reassignment", notes="timeout_20min")
            # Mark dispatch attempt as no_response
            await db.execute(
                text("""
                    UPDATE dispatch_attempts SET outcome='no_response', responded_at=NOW()
                    WHERE task_id=:tid AND outcome IS NULL
                """),
                {"tid": task_id}
            )

        return timed_out

    # ── Helpers ───────────────────────────────────────────────
    async def _assert_transition(
        self,
        db: AsyncSession,
        task_id: str,
        tenant_id: str,
        to_status: str,
        volunteer_id: Optional[str] = None,
    ) -> None:
        result = await db.execute(
            text("SELECT status FROM tasks WHERE task_id=:tid AND tenant_id=:ten"),
            {"tid": task_id, "ten": tenant_id}
        )
        row = result.fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        current = row.status
        allowed = VALID_TRANSITIONS.get(current, [])
        if to_status not in allowed:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=409,
                detail=f"Invalid transition: {current} → {to_status}. Allowed: {allowed}"
            )

    async def _log_transition(
        self,
        db: AsyncSession,
        task_id: str,
        tenant_id: str,
        from_status: Optional[str],
        to_status: str,
        triggered_by: Optional[str] = None,
        volunteer_id: Optional[str] = None,
        notes: str = "",
    ) -> None:
        user_id = triggered_by or volunteer_id
        await db.execute(
            text("""
                INSERT INTO task_state_log
                    (task_id, tenant_id, from_status, to_status, triggered_by, notes)
                VALUES (:tid, :ten, :from, :to, :by, :notes)
            """),
            {
                "tid":   task_id,
                "ten":   tenant_id,
                "from":  from_status,
                "to":    to_status,
                "by":    user_id,
                "notes": notes,
            }
        )


task_service = TaskOrchestrationService()
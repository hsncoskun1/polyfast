"""LiveValidator — validates whether discovered events are actually live.

This is the validation layer (v0.2.5) that sits between discovery (candidate)
and registry (authoritative state). It checks if an event is truly live
on Polymarket before allowing it to become ACTIVE.

Responsibilities:
- Check if a candidate/validating event is actually live
- Return validation result (valid/invalid/error)
- On success: registry can transition VALIDATING → ACTIVE
- On failure: event stays VALIDATING or moves to INACTIVE
- On source error: event stays VALIDATING, health incident produced

Does NOT:
- Manage registry state directly (→ caller/orchestrator)
- Fetch market data or PTB (→ v0.3.x)
- Evaluate trading rules (→ v0.4.x)
- Implement safe sync (→ v0.2.6)

Validation source:
- PublicMarketClient GET /events/{slug} or condition_id lookup
- This is a skeleton-level implementation
- Exact Polymarket endpoint format will be refined with live API testing
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from backend.auth_clients.public_client import PublicMarketClient
from backend.auth_clients.errors import ClientError
from backend.domain.startup_guard import HealthIncident, HealthSeverity
from backend.logging_config.service import get_logger, log_event

logger = get_logger("live_validator")


class ValidationResult(str, Enum):
    """Result of a live validation check."""
    VALID = "valid"           # Event is confirmed live
    INVALID = "invalid"       # Event is not live (closed, expired, not found)
    ERROR = "error"           # Validation source failed, cannot determine


@dataclass(frozen=True)
class ValidationOutcome:
    """Outcome of a single event live validation.

    Attributes:
        condition_id: The event being validated.
        result: VALID, INVALID, or ERROR.
        reason: Human-readable explanation.
        health_incident: If source failed, a HealthIncident for surfacing.
        validated_at: When validation was performed.
    """
    condition_id: str
    result: ValidationResult
    reason: str
    health_incident: HealthIncident | None = None
    validated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class LiveValidator:
    """Validates whether events are actually live on Polymarket.

    Uses PublicMarketClient to check event liveness. Does NOT transition
    registry state directly — returns ValidationOutcome for the caller
    to act on.

    Validation source: PublicMarketClient (no credentials needed).
    """

    def __init__(self, public_client: PublicMarketClient):
        self._client = public_client

    async def validate_event(self, condition_id: str, slug: str = "") -> ValidationOutcome:
        """Validate whether an event is actually live.

        Args:
            condition_id: Polymarket condition ID.
            slug: Event slug for URL-based lookup (optional).

        Returns:
            ValidationOutcome with result and reason.
        """
        try:
            is_live = await self._check_event_live(condition_id, slug)

            if is_live:
                log_event(
                    logger, logging.INFO,
                    f"Event validated as LIVE: {condition_id}",
                    entity_type="validation",
                    entity_id=condition_id,
                )
                return ValidationOutcome(
                    condition_id=condition_id,
                    result=ValidationResult.VALID,
                    reason="Event confirmed live on Polymarket",
                )
            else:
                log_event(
                    logger, logging.INFO,
                    f"Event validated as NOT LIVE: {condition_id}",
                    entity_type="validation",
                    entity_id=condition_id,
                )
                return ValidationOutcome(
                    condition_id=condition_id,
                    result=ValidationResult.INVALID,
                    reason="Event not live on Polymarket (closed, expired, or not found)",
                )

        except ClientError as e:
            incident = HealthIncident(
                severity=HealthSeverity.WARNING,
                category="validation",
                message=f"Live validation failed for {condition_id}: {e}",
                suggested_action="Check network connectivity and Polymarket API availability.",
            )
            log_event(
                logger, logging.WARNING,
                f"Live validation source error for {condition_id}: {e}",
                entity_type="validation",
                entity_id=condition_id,
                payload={"error_category": e.category.value},
            )
            return ValidationOutcome(
                condition_id=condition_id,
                result=ValidationResult.ERROR,
                reason=f"Validation source error: {e}",
                health_incident=incident,
            )

        except Exception as e:
            incident = HealthIncident(
                severity=HealthSeverity.WARNING,
                category="validation",
                message=f"Unexpected validation error for {condition_id}: {e}",
                suggested_action="Check Polymarket API response format.",
            )
            log_event(
                logger, logging.ERROR,
                f"Unexpected validation error for {condition_id}: {e}",
                entity_type="validation",
                entity_id=condition_id,
            )
            return ValidationOutcome(
                condition_id=condition_id,
                result=ValidationResult.ERROR,
                reason=f"Unexpected error: {e}",
                health_incident=incident,
            )

    async def _check_event_live(self, condition_id: str, slug: str) -> bool:
        """Check if event is live via Polymarket Gamma API.

        Uses slug-based lookup (GET /events?slug=XXX).
        Based on live API validation: /events/{id} returns 422 for conditionId,
        slug-based query parameter is the correct approach.

        Raises:
            ClientError: On API failure.
        """
        if slug:
            response = await self._client.get("/events", params={"slug": slug})
        else:
            # Fallback: try condition_id based search
            response = await self._client.get("/events", params={"slug": condition_id})

        data = response.json()

        # Gamma API returns list of events
        if isinstance(data, list):
            if not data:
                return False
            event = data[0]
            closed = event.get("closed", True)
            active = event.get("active", False)
            return (not closed) or active

        if isinstance(data, dict):
            closed = data.get("closed", True)
            active = data.get("active", False)
            return (not closed) or active

        return False

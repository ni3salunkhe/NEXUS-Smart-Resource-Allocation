from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime
from enum import Enum


# ── Enums ─────────────────────────────────────────────────────
class DwellingType(str, Enum):
    permanent      = "permanent"
    semi_permanent = "semi_permanent"
    temporary      = "temporary"
    open_space     = "open_space"

class EconomicTier(str, Enum):
    below_poverty = "below_poverty"
    marginal      = "marginal"
    low           = "low"
    medium        = "medium"

class HouseholdStatus(str, Enum):
    active      = "active"
    relocated   = "relocated"
    dissolved   = "dissolved"
    merged_away = "merged_away"
    opted_out   = "opted_out"

class MemberRole(str, Enum):
    head      = "head"
    spouse    = "spouse"
    child     = "child"
    parent    = "parent"
    dependent = "dependent"
    other     = "other"

class AgeBracket(str, Enum):
    infant  = "infant"
    child   = "child"
    youth   = "youth"
    adult   = "adult"
    elderly = "elderly"

class ConsentType(str, Enum):
    data_collection   = "data_collection"
    location_sharing  = "location_sharing"
    cross_org_linking = "cross_org_linking"
    analytics         = "analytics"
    photo             = "photo"

class ConsentMethod(str, Enum):
    verbal_witnessed = "verbal_witnessed"
    signed_form      = "signed_form"
    digital_app      = "digital_app"

class LinkStatus(str, Enum):
    proposed  = "proposed"
    active    = "active"
    rejected  = "rejected"
    revoked   = "revoked"

class HHEventType(str, Enum):
    need_reported        = "need_reported"
    need_resolved        = "need_resolved"
    task_dispatched      = "task_dispatched"
    task_completed       = "task_completed"
    member_added         = "member_added"
    member_removed       = "member_removed"
    vulnerability_updated= "vulnerability_updated"
    consent_changed      = "consent_changed"
    assistance_received  = "assistance_received"
    location_updated     = "location_updated"
    merged               = "merged"
    linked               = "linked"
    opted_out            = "opted_out"


# ── Location ──────────────────────────────────────────────────
class LocationInput(BaseModel):
    latitude:    Optional[float] = Field(None, ge=-90,  le=90)
    longitude:   Optional[float] = Field(None, ge=-180, le=180)
    confidence:  float           = Field(0.5,  ge=0, le=1)
    description: Optional[str]  = None
    landmarks:   List[str]       = []

    @model_validator(mode="after")
    def lat_lon_together(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both latitude and longitude or neither")
        return self


# ── Member schemas ─────────────────────────────────────────────
class MemberCreate(BaseModel):
    role_in_household:  Optional[MemberRole]   = None
    age_bracket:        Optional[AgeBracket]   = None
    gender:             Optional[str]          = None
    is_primary_contact: bool                   = False
    vulnerability_flags: dict                  = {}
    # PII: name + phone go to PII vault, not DB
    name:  Optional[str] = Field(None, exclude=True)
    phone: Optional[str] = Field(None, exclude=True)


class MemberResponse(BaseModel):
    member_id:           UUID
    household_id:        UUID
    role_in_household:   Optional[str]
    age_bracket:         Optional[str]
    is_primary_contact:  bool
    vulnerability_flags: dict
    is_present:          bool
    added_at:            datetime
    removed_at:          Optional[datetime]

    class Config:
        from_attributes = True


# ── Household schemas ─────────────────────────────────────────
class HouseholdCreate(BaseModel):
    ward_id:       Optional[str]      = None
    location:      Optional[LocationInput] = None
    dwelling_type: Optional[DwellingType]  = None
    economic_tier: Optional[EconomicTier]  = None
    members:       List[MemberCreate]  = []


class HouseholdUpdate(BaseModel):
    ward_id:       Optional[str]           = None
    location:      Optional[LocationInput] = None
    dwelling_type: Optional[DwellingType]  = None
    economic_tier: Optional[EconomicTier]  = None
    landmark_tags: Optional[List[str]]     = None


class HouseholdResponse(BaseModel):
    household_id:          UUID
    global_household_id:   Optional[UUID]
    tenant_id:             UUID
    ward_id:               Optional[str]
    location_confidence:   float
    location_description:  Optional[str]
    landmark_tags:         List[str]
    dwelling_type:         Optional[str]
    total_members:         int
    vulnerability_score:   float
    vulnerability_flags:   dict
    economic_tier:         Optional[str]
    total_needs_reported:  int
    total_tasks_completed: int
    last_need_reported_at: Optional[datetime]
    last_assistance_at:    Optional[datetime]
    crisis_frequency:      float
    status:                str
    data_quality_score:    float
    created_at:            datetime
    updated_at:            datetime
    members:               List[MemberResponse] = []

    class Config:
        from_attributes = True


# ── Identity Resolution schemas ───────────────────────────────
class IdentityResolutionRequest(BaseModel):
    """Input for resolving a reported need to a household."""
    # Stage 1: exact signals
    phone_number:      Optional[str]  = None
    known_household_id: Optional[UUID] = None
    # Stage 2: geospatial
    latitude:          Optional[float] = None
    longitude:         Optional[float] = None
    # Stage 3: fuzzy
    location_description: Optional[str] = None
    landmark_tags:     List[str]        = []
    family_size:       Optional[int]    = None
    dwelling_type:     Optional[str]    = None
    vulnerability_flags: dict           = {}
    description_text:  Optional[str]   = None
    tenant_id:         str              = ""


class CandidateMatch(BaseModel):
    household_id:    UUID
    confidence:      float
    match_stage:     int       # 1-4
    match_signals:   dict      # which signals fired
    distance_m:      Optional[float] = None
    household:       Optional[HouseholdResponse] = None


class ResolutionResult(BaseModel):
    status:          str   # "auto_linked" | "review_required" | "new_household"
    household_id:    Optional[UUID] = None
    confidence:      float
    candidates:      List[CandidateMatch] = []
    resolution_id:   str   # UUID for tracking


# ── Consent schemas ───────────────────────────────────────────
class ConsentCreate(BaseModel):
    consent_type:       ConsentType
    scope:              dict = {
        "tenants_allowed": [],
        "purposes":        [],
        "data_fields_allowed": [],
    }
    expires_at:         Optional[datetime] = None
    collection_method:  Optional[ConsentMethod] = None
    language_used:      Optional[str]      = None
    primary_contact_ref: Optional[UUID]    = None


class ConsentResponse(BaseModel):
    consent_id:       UUID
    household_id:     UUID
    consent_type:     str
    scope:            dict
    granted_at:       datetime
    expires_at:       Optional[datetime]
    revoked_at:       Optional[datetime]
    opt_out:          bool
    collection_method: Optional[str]
    language_used:    Optional[str]

    class Config:
        from_attributes = True


# ── Cross-tenant link schemas ─────────────────────────────────
class CrossTenantLinkCreate(BaseModel):
    household_id_tenant_b: UUID
    tenant_b:              UUID
    link_confidence:       float
    fields_shared:         List[str] = []
    consent_id_a:          Optional[UUID] = None
    consent_id_b:          Optional[UUID] = None


class CrossTenantLinkResponse(BaseModel):
    link_id:               UUID
    household_id_tenant_a: UUID
    household_id_tenant_b: UUID
    global_household_id:   UUID
    link_confidence:       float
    link_method:           str
    link_status:           str
    fields_shared:         List[str]
    created_at:            datetime
    approved_at:           Optional[datetime]

    class Config:
        from_attributes = True


# ── History schemas ───────────────────────────────────────────
class HouseholdHistoryResponse(BaseModel):
    event_id:        UUID
    household_id:    UUID
    event_type:      str
    event_timestamp: datetime
    event_payload:   dict
    related_need_id: Optional[UUID]
    related_task_id: Optional[UUID]

    class Config:
        from_attributes = True


# ── Merge schemas ─────────────────────────────────────────────
class MergeRequest(BaseModel):
    source_household_id: UUID   # will be merged into target
    target_household_id: UUID   # survives
    merge_reason:        str


class SearchRequest(BaseModel):
    query:          Optional[str]   = None
    ward_id:        Optional[str]   = None
    landmark:       Optional[str]   = None
    status:         Optional[str]   = "active"
    has_child:      Optional[bool]  = None
    has_elderly:    Optional[bool]  = None
    min_vuln_score: Optional[float] = None
    latitude:       Optional[float] = None
    longitude:      Optional[float] = None
    radius_m:       int             = 500
    limit:          int             = Field(20, le=100)
    offset:         int             = 0
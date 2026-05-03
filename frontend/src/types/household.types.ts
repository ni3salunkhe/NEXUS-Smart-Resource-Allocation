export type DwellingType = 'permanent' | 'semi-permanent' | 'temporary' | 'open-space'
export type EconomicTier = 'below_poverty' | 'marginal' | 'low' | 'medium'
export type HouseholdStatus = 'active' | 'relocated' | 'dissolved' | 'merged_away' | 'opted_out'
export type AgeBracket = 'infant' | 'child' | 'youth' | 'adult' | 'elderly'
export type MemberRole = 'head' | 'spouse' | 'child' | 'parent' | 'dependent' | 'other'

export interface VulnerabilityFlags {
  has_child: boolean
  has_elderly: boolean
  has_disabled: boolean
  has_pregnant: boolean
  chronic_illness: boolean
  single_parent: boolean
}

export interface MemberVulnerabilityFlags {
  disabled: boolean
  chronic_illness: boolean
  pregnant: boolean
  malnourished: boolean
  mental_health: boolean
}

export interface HouseholdMember {
  member_id: string
  household_id: string
  role_in_household: MemberRole
  age_bracket: AgeBracket
  gender?: string
  is_primary_contact: boolean
  vulnerability_flags: MemberVulnerabilityFlags
  is_present: boolean
  added_at: string
  removed_at?: string
}

export interface Household {
  household_id: string
  global_household_id?: string
  tenant_id: string
  ward_id: string
  location: { lat: number; lng: number }
  location_confidence: number        // 0–1
  location_description: string       // verbatim, never overwrite
  landmark_tags: string[]
  dwelling_type: DwellingType
  total_members: number
  vulnerability_score: number        // 0–1
  vulnerability_flags: VulnerabilityFlags
  economic_tier: EconomicTier
  total_needs_reported: number
  total_tasks_completed: number
  last_need_reported_at?: string
  last_assistance_at?: string
  total_assistance_value: number
  assistance_categories: string[]
  crisis_frequency: number           // needs per month, 6-month rolling
  status: HouseholdStatus
  merged_into?: string
  data_quality_score: number         // 0–1
  created_at: string
  updated_at: string
  members?: HouseholdMember[]
}

export interface HouseholdHistoryEvent {
  event_id: string
  household_id: string
  event_type:
    | 'need_reported' | 'need_resolved' | 'task_dispatched'
    | 'task_completed' | 'member_added' | 'member_removed'
    | 'vulnerability_updated' | 'consent_changed'
    | 'assistance_received' | 'location_updated' | 'merged' | 'linked'
  event_timestamp: string
  event_payload: Record<string, unknown>
  related_need_id?: string
  related_task_id?: string
  triggered_by: string
}

export interface HouseholdMatchResult {
  household_id?: string
  provisional_id?: string
  confidence: number                 // 0–1
  match_stage: 1 | 2 | 3 | 4
  requires_review: boolean
  is_new: boolean
}

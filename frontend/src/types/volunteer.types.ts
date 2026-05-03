export type SkillVerificationStatus = 'verified' | 'unverified' | 'pending'

export interface VolunteerSkill {
  skill: string
  verified: boolean
  credential_ref?: string
}

export interface Volunteer {
  volunteer_id: string
  tenant_id: string
  location_home: { lat: number; lng: number }
  location_current?: { lat: number; lng: number }
  location_updated_at?: string
  skills: VolunteerSkill[]
  languages: string[]               // ISO 639-1
  availability_schedule: Record<string, unknown>
  max_distance_km: number
  total_deployments: number
  outcome_rating_avg: number
  burnout_risk_score: number        // 0–1
  consecutive_active_days: number
  active: boolean
  verified: boolean
  ngo_affiliation?: string
  // PII comes separately via pii_ref — names/phone never inline
  display_name?: string             // resolved from PII vault, if permitted
}

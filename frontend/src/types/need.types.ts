import { VulnerabilityFlags } from './household.types'

export type NeedSourceType =
  'paper' | 'whatsapp' | 'mobile' | 'csv' | 'api' | 'field_observation'

export type NeedCategory =
  'food' | 'health' | 'shelter' | 'education' | 'livelihood'
  | 'water' | 'sanitation' | 'mental_health' | 'legal'
  | 'documentation' | 'mobility' | 'other'

export type NeedStatus =
  'unverified' | 'verified' | 'assigned' | 'in_progress'
  | 'resolved' | 'closed' | 'duplicate'

export interface NeedRecord {
  need_id: string
  source_type: NeedSourceType
  reported_by: string
  reported_at: string
  household_id: string
  household_resolution_confidence: number
  location: { lat: number; lng: number }
  ward_id: string
  category: NeedCategory
  subcategory: string
  description: string               // normalized
  original_description: string      // verbatim, preserved
  detected_language: string
  severity_score: number            // 0–1
  urgency_score: number             // 0–1, refreshed continuously
  beneficiary_count: number
  vulnerability_flags: VulnerabilityFlags
  status: NeedStatus
  verified_by?: string
  verified_at?: string
  assigned_task_id?: string
  resolution_notes?: string
  is_chronic: boolean
  created_at: string
  updated_at: string
}

export interface UrgencyScore {
  score_id: string
  need_id: string
  household_id: string
  score: number
  component_scores: {
    severity: number
    recency: number
    vulnerability: number
    duration: number
    reliability: number
    coverage: number
  }
  chronic_risk_floor_applied: boolean
  time_decay_escalations: number
  computed_at: string
  expires_at: string
}

export type TaskStatus =
  'unassigned' | 'dispatched' | 'accepted' | 'in_progress'
  | 'completed' | 'cancelled' | 'needs_reassignment'

export type OutcomeStatus =
  'need_fully_resolved' | 'need_partially_met' | 'unresolved' | 'escalated'

export interface Task {
  task_id: string
  need_id: string
  household_id: string
  match_id: string
  assigned_volunteer_id?: string
  status: TaskStatus
  dispatch_attempts: number
  accepted_at?: string
  started_at?: string
  completed_at?: string
  outcome_status?: OutcomeStatus
  outcome_notes?: string
  materials_provided?: Record<string, unknown>
  new_needs_observed?: Record<string, unknown>
  follow_up_required: boolean
  follow_up_date?: string
  volunteer_rating?: number
  household_rating?: number
}

export interface MatchRequest {
  match_id: string
  task_id: string
  need_id: string
  household_id: string
  requirement_vector: Record<string, number>
  candidate_pool_size: number
  top_matches: Array<{
    volunteer_id: string
    similarity_score: number
    score_breakdown: Record<string, number>
    rank: number
  }>
  selected_volunteer_id?: string
  selection_method: 'algorithm_top' | 'coordinator_override' | 'manual'
  override_reason?: string
  computed_at: string
}

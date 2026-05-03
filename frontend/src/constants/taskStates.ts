// Task state machine — mirrors backend VALID_TRANSITIONS exactly
export type TaskState =
  | 'unassigned'
  | 'dispatched'
  | 'accepted'
  | 'in_progress'
  | 'completed'
  | 'cancelled'
  | 'needs_reassignment'
  | 'closed';

export const VALID_TRANSITIONS: Record<TaskState, TaskState[]> = {
  unassigned:         ['dispatched'],
  dispatched:         ['accepted', 'cancelled', 'needs_reassignment'],
  accepted:           ['in_progress', 'cancelled'],
  in_progress:        ['completed', 'needs_reassignment'],
  completed:          ['closed'],
  cancelled:          ['dispatched'],
  needs_reassignment: ['dispatched'],
  closed:             [], // terminal
};

export function canTransition(from: TaskState, to: TaskState): boolean {
  return VALID_TRANSITIONS[from]?.includes(to) ?? false;
}

export const TASK_STATE_LABELS: Record<TaskState, string> = {
  unassigned:         'Unassigned',
  dispatched:         'Dispatched',
  accepted:           'Accepted',
  in_progress:        'In Progress',
  completed:          'Completed',
  cancelled:          'Cancelled',
  needs_reassignment: 'Needs Reassignment',
  closed:             'Closed',
};

export const TASK_STATE_COLORS: Record<TaskState, string> = {
  unassigned:         'bg-gray-100 text-gray-600',
  dispatched:         'bg-blue-100 text-blue-700',
  accepted:           'bg-indigo-100 text-indigo-700',
  in_progress:        'bg-amber-100 text-amber-700',
  completed:          'bg-green-100 text-green-700',
  cancelled:          'bg-red-100 text-red-600',
  needs_reassignment: 'bg-orange-100 text-orange-700',
  closed:             'bg-slate-200 text-slate-600',
};

// Outcome statuses — backend enum
export type OutcomeStatus = 'need_fully_met' | 'partially_met' | 'unresolved' | 'follow_up_required';

export const OUTCOME_LABELS: Record<OutcomeStatus, string> = {
  need_fully_met:      'Fully Met',
  partially_met:       'Partially Met',
  unresolved:          'Unresolved',
  follow_up_required:  'Follow-up Required',
};

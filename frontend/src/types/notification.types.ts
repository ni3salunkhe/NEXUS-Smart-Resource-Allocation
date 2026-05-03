export type NotificationEventType =
  | 'need.created'
  | 'need.urgency_updated'
  | 'need.status_changed'
  | 'task.assigned'
  | 'task.status_changed'
  | 'task.created'
  | 'task.dispatched'
  | 'task.accepted'
  | 'task.started'
  | 'task.completed'
  | 'task.cancelled'
  | 'volunteer.location_updated'
  | 'household.linked'
  | 'household.created'
  | 'household.merged'
  | 'household.consent_updated'
  | 'analytics.gap_report.generated'
  | 'alert.escalation'
  | 'burnout.threshold'
  | 'consent.expiry_warning'
  | 'system.sla_breach'

export interface AppNotification {
  id: string
  event_type: NotificationEventType
  title: string
  description: string
  timestamp: string
  read: boolean
  action_label?: string
  action_payload?: Record<string, unknown>
  severity: 'info' | 'warning' | 'danger' | 'success'
}

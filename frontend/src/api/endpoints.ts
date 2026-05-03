import { apiClient } from './client';
import type { NeedRecord, UrgencyScore } from '../types/need.types';
import type { MatchRequest, Task } from '../types/task.types';
import type { Household, HouseholdHistoryEvent } from '../types/household.types';
import type { Volunteer } from '../types/volunteer.types';

// ── Tenants & Auth (→ Auth :8000) ────────────────────────────
export const TenantAPI = {
  list: () =>
    apiClient.get('/api/proxy/tenants'),
  listPublic: () =>
    apiClient.get('/proxy/auth/tenants/public'),
  create: (data: any) =>
    apiClient.post('/api/proxy/tenants', data),
};

export const AuthAPI = {
  login: (email: string, password: string) =>
    apiClient.post('/proxy/auth/login', { email, password }),
  signup: (data: { email: string; password: string; display_name: string; tenant_id: string; role?: string }) =>
    apiClient.post('/proxy/auth/signup', data), // Assuming proxy passes this to auth service
  refresh: (refresh_token: string) =>
    apiClient.post('/proxy/auth/refresh', { refresh_token }),
};

// ── Household Registry (→ Registry :8001) ────────────────────
export const HouseholdAPI = {
  create: (data: any) =>
    apiClient.post('/api/registry/households', data),
  list: (params?: { ward_id?: string; status?: string; limit?: number; offset?: number }) =>
    apiClient.get('/api/registry/households', { params }),
  search: (data: any) =>
    apiClient.post('/api/registry/households/search', data),
  get: (id: string, includeMembers: boolean = true) =>
    apiClient.get(`/api/registry/households/${id}?include_members=${includeMembers}`),
  update: (id: string, data: any) =>
    apiClient.patch(`/api/registry/households/${id}`, data),
  getHistory: (id: string) =>
    apiClient.get<HouseholdHistoryEvent[]>(`/api/registry/households/${id}/history`),
  getConsent: (id: string) =>
    apiClient.get(`/api/registry/households/${id}/consent`),
  merge: (data: { source_id: string; target_id: string; reason: string }) =>
    apiClient.post('/api/registry/households/merge', data),
  addConsent: (id: string, data: any) =>
    apiClient.post(`/api/registry/households/${id}/consent`, data),
  revokeConsent: (id: string, consentId: string, reason: string) =>
    apiClient.delete(`/api/registry/households/${id}/consent/${consentId}?reason=${encodeURIComponent(reason)}`),
  optOut: (id: string) =>
    apiClient.post(`/api/registry/households/${id}/opt-out`),
  proposeLink: (id: string, data: any) =>
    apiClient.post(`/api/registry/households/${id}/links`, data),
  approveLink: (linkId: string) =>
    apiClient.post(`/api/registry/links/${linkId}/approve`),
};

// ── Global Search (→ Registry :8001) ─────────────────────────
export const SearchAPI = {
  global: (q: string) =>
    apiClient.get('/api/registry/search/global', { params: { q } }),
};

// ── Identity Resolution (→ Registry :8001) ───────────────────
export const IdentityAPI = {
  resolve: (data: any) =>
    apiClient.post('/api/registry/resolve', data),
};

// ── Wards (→ Registry :8001) ─────────────────────────────────
export const WardAPI = {
  list: () =>
    apiClient.get('/api/registry/wards'),
};

// ── Needs & Ingestion (→ Ingestion :8002) ────────────────────
export const NeedAPI = {
  list: (params?: { status?: string; category?: string; ward_id?: string; limit?: number; offset?: number }) =>
    apiClient.get<NeedRecord[]>('/api/ingestion/needs', { params }),
  get: (need_id: string) =>
    apiClient.get<NeedRecord>(`/api/ingestion/needs/${need_id}`),
  getReviewQueue: (limit: number = 20, review_type?: string) =>
    apiClient.get('/api/ingestion/review', { params: { limit, review_type } }),
  approveReview: (review_id: string, data?: any) =>
    apiClient.post(`/api/ingestion/review/${review_id}/approve`, data || {}),
  rejectReview: (review_id: string, data?: any) =>
    apiClient.post(`/api/ingestion/review/${review_id}/reject`, data || {}),
  createHouseholdFromReview: (review_id: string, data: any) =>
    apiClient.post(`/api/ingestion/review/${review_id}/create-household`, data), // GAP-04
  ingestMobile: (data: {
    category: string; description: string; location_text?: string;
    latitude?: number; longitude?: number; beneficiary_count?: number;
    known_household_id?: string; reported_at?: string; language: string;
    vulnerability_flags?: Record<string, boolean>;
  }) => apiClient.post('/api/ingestion/ingest/mobile', data),
  ingestText: (data: {
    text: string; source: 'whatsapp' | 'sms'; sender_phone?: string;
    known_household_id?: string; reported_at?: string; language_hint?: string;
  }) => apiClient.post('/api/ingestion/ingest/text', data),
  ingestImage: (file: File, language_hints?: string, known_household_id?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post('/api/ingestion/ingest/image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params: { language_hints, known_household_id },
    });
  },
  ingestCsv: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post('/api/ingestion/ingest/csv', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  getIngestStatus: (raw_id: string) =>
    apiClient.get(`/api/ingestion/ingest/status/${raw_id}`), // GAP-08
};

// ── Volunteers (→ Coordination :8003) ────────────────────────
export const VolunteerAPI = {
  list: (params?: { active?: boolean; ward_id?: string; skill?: string; limit?: number }) =>
    apiClient.get<Volunteer[]>('/api/coordination/volunteers', { params }),
  get: (id: string) =>
    apiClient.get<Volunteer>(`/api/coordination/volunteers/${id}`),
  create: (data: any) =>
    apiClient.post('/api/coordination/volunteers', data),
  update: (id: string, data: any) =>
    apiClient.patch(`/api/coordination/volunteers/${id}`, data),
  getAvailability: (id: string) =>
    apiClient.get(`/api/coordination/volunteers/${id}/availability`),
  getBurnout: (id: string) =>
    apiClient.get(`/api/coordination/volunteers/${id}/burnout`),
  pingLocation: (id: string, data: { latitude: number; longitude: number }) =>
    apiClient.post(`/api/coordination/volunteers/${id}/location`, data),
  getNotificationPrefs: (id: string) =>
    apiClient.get(`/api/coordination/volunteers/${id}/notifications`),
  testNotification: (id: string) =>
    apiClient.post(`/api/coordination/volunteers/${id}/notifications/test`),
};

// ── Tasks & Dispatch (→ Coordination :8003) ──────────────────
export const TaskAPI = {
  list: (params?: { status?: string; limit?: number; offset?: number }) =>
    apiClient.get<Task[]>('/api/coordination/tasks', { params }),
  get: (task_id: string) =>
    apiClient.get<Task>(`/api/coordination/tasks/${task_id}`),
  create: (data: { need_id: string; household_id?: string }) =>
    apiClient.post<Task>('/api/coordination/tasks', data),
  getMatches: (task_id: string, radius_km: number = 15) =>
    apiClient.get(`/api/coordination/tasks/${task_id}/matches`, { params: { radius_km } }),
  dispatch: (task_id: string, data: { volunteer_id: string; auto_dispatch?: boolean; briefing_language?: string }) =>
    apiClient.post(`/api/coordination/tasks/${task_id}/dispatch`, data),
  accept: (task_id: string, volunteer_id: string) =>
    apiClient.post(`/api/coordination/tasks/${task_id}/accept?volunteer_id=${volunteer_id}`),
  start: (task_id: string, volunteer_id: string) =>
    apiClient.post(`/api/coordination/tasks/${task_id}/start?volunteer_id=${volunteer_id}`),
  complete: (task_id: string, volunteer_id: string, data: any) =>
    apiClient.post(`/api/coordination/tasks/${task_id}/complete?volunteer_id=${volunteer_id}`, data),
  close: (task_id: string, data?: { volunteer_rating?: number }) =>
    apiClient.post(`/api/coordination/tasks/${task_id}/close`, data || {}),
  decline: (task_id: string, volunteer_id: string, reason: string = '') =>
    apiClient.post(`/api/coordination/tasks/${task_id}/decline?volunteer_id=${volunteer_id}`, { reason }),
  recordOverride: (data: any) =>
    apiClient.post('/api/coordination/coordination/overrides/record', data),
};

// ── Intelligence Service (/priority-queue, /score, /heatmap, etc) ──
export const IntelligenceAPI = {
  getPriorityQueue: (params?: { limit?: number; offset?: number; category?: string; ward_id?: string; vulnerability_filter?: string }) =>
    apiClient.get('/api/intelligence/priority-queue', { params }),
  getEscalations: () =>
    apiClient.get('/api/intelligence/escalations'),
  recomputeScore: (need_id: string) =>
    apiClient.post(`/api/intelligence/score/${need_id}`),
  batchRecompute: () =>
    apiClient.post('/api/intelligence/score/batch'),
  getHeatmap: (params?: { category?: string; hours_back?: number; geo_precision?: number }) =>
    apiClient.get('/api/intelligence/heatmap', { params }),
  getWardStats: (ward_ids?: string) =>
    apiClient.get('/api/intelligence/ward-stats', { params: { ward_ids } }),
  refreshWardStats: () =>
    apiClient.post('/api/intelligence/ward-stats/refresh'),
  generateGapReport: () =>
    apiClient.post('/api/intelligence/gap-report/generate'),
  getGapReport: () =>
    apiClient.get('/api/intelligence/gap-report'),
  getResourceDeserts: (urgency_threshold?: number) =>
    apiClient.get('/api/intelligence/resource-deserts', { params: { urgency_threshold } }),
  getWeights: () =>
    apiClient.get('/api/intelligence/weights'),
  updateWeights: (data: any) =>
    apiClient.put('/api/intelligence/weights', data),
  getScoreHistory: (need_id: string, limit?: number) =>
    apiClient.get(`/api/intelligence/score-history/${need_id}`, { params: { limit } }),
  search: (params: { q: string; category?: string; ward_id?: string; min_urgency?: number; limit?: number }) =>
    apiClient.get('/api/intelligence/search', { params }),
};

// ── Analytics Service ────────────────────────────────────────
export const AnalyticsAPI = {
  computeMetrics: (params?: { period_start?: string; period_end?: string; period_type?: string }) =>
    apiClient.post('/api/analytics/metrics/compute', null, { params }),
  getImpactMetrics: (params?: { period_type?: string; limit?: number }) =>
    apiClient.get('/api/analytics/metrics/impact', { params }),
  getHouseholdImprovement: (params?: { window_days?: number; trend_filter?: string; limit?: number }) =>
    apiClient.get('/api/analytics/households/improvement', { params }),
  getHouseholdImprovementById: (id: string) =>
    apiClient.get(`/api/analytics/households/${id}/improvement`),
  getVolunteerPerformance: (params?: { limit?: number }) =>
    apiClient.get('/api/analytics/volunteers/performance', { params }),
  getVolunteerPerformanceById: (id: string) =>
    apiClient.get(`/api/analytics/volunteers/${id}/performance`),
  getOverridesSummary: (days_back?: number) =>
    apiClient.get('/api/analytics/overrides/summary', { params: { days_back } }),
  getOverridesPatterns: (days_back?: number) =>
    apiClient.get('/api/analytics/overrides/patterns', { params: { days_back } }),
  getDuplicationRate: (days_back?: number) =>
    apiClient.get('/api/analytics/duplication-rate', { params: { days_back } }),
  processFeedback: (task_id: string) =>
    apiClient.post(`/api/analytics/feedback/process/${task_id}`),
  getPendingFeedback: (limit?: number) =>
    apiClient.get('/api/analytics/feedback/pending', { params: { limit } }),
  getFunderReport: (period_months?: number) =>
    apiClient.get('/api/analytics/funder-report', { params: { period_months } }),
};

// ── Health Checks ────────────────────────────────────────────
export const HealthAPI = {
  registry: () => apiClient.get('/api/registry/health'),
  ingestion: () => apiClient.get('/api/ingestion/health'),
  coordination: () => apiClient.get('/api/coordination/health'),
  intelligence: () => apiClient.get('/api/intelligence/health'),
  analytics: () => apiClient.get('/api/analytics/health'),
};

// ── Settings (→ Registry :8001) ──────────────────────────────
export const SettingsAPI = {
  getCrossTenantPolicies: () =>
    apiClient.get('/api/registry/settings/cross-tenant-policies'), // GAP-10
  updatePolicy: (partnerId: string, data: any) =>
    apiClient.patch(`/api/registry/settings/cross-tenant-policies/${partnerId}`, data), // GAP-10
};

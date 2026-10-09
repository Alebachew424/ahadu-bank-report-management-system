import api from './index';
import type { ReportRequest, RequestCreate, RequestUpdate } from '../types/types';

export interface RequestFeedback {
  id: number;
  request_id: number;
  requester_id: number;
  quality_rating: number;
  timeliness_rating: number;
  comment: string | null;
  created_at: string;
}

export interface SearchParams {
  q?:             string;
  status?:        string;   // comma-separated
  priority?:      string;   // comma-separated
  department_id?: number;
  requester_id?:  number;
  assignee_id?:   number;
  date_from?:     string;
  date_to?:       string;
  overdue_only?:  boolean;
  sort_by?:       'created_at' | 'due_date' | 'priority' | 'status_id';
  sort_dir?:      'asc' | 'desc';
  skip?:          number;
  limit?:         number;
}

export const requestsAPI = {
  // ── lookups ──────────────────────────────────────────────────────────────
  listTypes: () =>
    api.get<{ id: number; name: string; description: string | null; form_schema: Record<string, unknown>; sla_hours: number | null }[]>(
      '/requests/types',
    ),

  listDepartments: () =>
    api.get<{ id: number; name: string }[]>('/requests/departments'),

  previousResponse: (requestTypeId: number) =>
    api.get<{
      ticket_id: number;
      title: string;
      description: string | null;
      status: string;
      closed_at: string;
      attachments: { id: number; file_name: string; is_final: boolean; version: number }[];
      comments: { id: number; body: string; created_at: string }[];
    } | null>(`/requests/previous-response`, { params: { request_type_id: requestTypeId } }),

  // ── CRUD ─────────────────────────────────────────────────────────────────
  list: (params?: { skip?: number; limit?: number }) =>
    api.get<ReportRequest[]>('/requests/', { params }),

  search: (params: SearchParams) =>
    api.get<{ total: number; skip: number; limit: number; results: ReportRequest[] }>(
      '/requests/search', { params }
    ),

  create: (data: RequestCreate) => api.post<ReportRequest>('/requests/', data),

  get: (id: number) => api.get<ReportRequest>(`/requests/${id}`),

  update: (id: number, data: RequestUpdate) =>
    api.put<ReportRequest>(`/requests/${id}`, data),

  getSla: (id: number) =>
    api.get<{
      sla_deadline: string | null;
      sla_hours_remaining: number | null;
      sla_overdue: boolean;
      sla_breached: boolean;
    }>(`/requests/${id}/sla`),

  // ── workflow actions ──────────────────────────────────────────────────────
  deptApprove: (id: number) => api.post<ReportRequest>(`/requests/${id}/dept-approve`),
  deptReject:  (id: number) => api.post<ReportRequest>(`/requests/${id}/dept-reject`),
  assign: (id: number, analystId: number) =>
    api.post<ReportRequest>(`/requests/${id}/assign`, null, { params: { analyst_id: analystId } }),
  start:                (id: number) => api.post<ReportRequest>(`/requests/${id}/start`),
  resolve:              (id: number) => api.post<ReportRequest>(`/requests/${id}/resolve`),
  requestClarification: (id: number) => api.post<ReportRequest>(`/requests/${id}/request-clarification`),
  resume:               (id: number) => api.post<ReportRequest>(`/requests/${id}/resume`),
  cancel:               (id: number) => api.post<ReportRequest>(`/requests/${id}/cancel`),

  // ── feedback ──────────────────────────────────────────────────────────────
  createFeedback: (
    id: number,
    data: Pick<RequestFeedback, 'quality_rating' | 'timeliness_rating' | 'comment'>,
  ) => api.post<RequestFeedback>(`/requests/${id}/feedback`, data),

  getFeedback: (id: number) => api.get<RequestFeedback>(`/requests/${id}/feedback`),
};

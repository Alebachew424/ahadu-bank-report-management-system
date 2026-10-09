import api from './index';

interface AuditListParams {
  search?:      string;
  action?:      string;
  entity_type?: string;
  entity_id?:   number;
  user_id?:     number;
  date_from?:   string;
  date_to?:     string;
  skip?:        number;
  limit?:       number;
}

export const auditAPI = {
  list: (params?: AuditListParams) =>
    api.get<{
      total: number;
      skip: number;
      limit: number;
      results: {
        id: number;
        user_id: number | null;
        user_email: string | null;
        action: string;
        entity_type: string;
        entity_id: number | null;
        old_value: Record<string, unknown> | null;
        new_value: Record<string, unknown> | null;
        description: string | null;
        ip_address: string | null;
        created_at: string;
      }[];
    }>('/admin/audit-logs', { params }),

  get: (id: number) =>
    api.get(`/admin/audit-logs/${id}`),

  meta: () =>
    api.get<{ actions: string[]; entity_types: string[] }>('/admin/audit-logs-meta'),

  /** Opens CSV download in a new tab using the current token */
  exportUrl: (params?: Omit<AuditListParams, 'skip' | 'limit'>) => {
    const token = localStorage.getItem('access_token') ?? '';
    const base  = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1');
    const qs    = new URLSearchParams();
    if (params?.search)      qs.set('search',      params.search);
    if (params?.action)      qs.set('action',      params.action);
    if (params?.entity_type) qs.set('entity_type', params.entity_type);
    if (params?.date_from)   qs.set('date_from',   params.date_from);
    if (params?.date_to)     qs.set('date_to',     params.date_to);
    // Browsers can't send Authorization header via window.open, so we append
    // the token as a query param for the export endpoint only.
    qs.set('token', token);
    window.open(`${base}/admin/audit-logs/export?${qs.toString()}`, '_blank');
  },
};

import api from './index';

export interface ManagedUser {
  id: number;
  email: string;
  full_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  role_id: number | null;
  role_name: string | null;
  department_id: number | null;
}

export interface ManagedRole { id: number; name: string; permissions: string[]; role_type: 'Manager' | 'Officer'; }
export interface ManagedDepartment { id: number; name: string; manager_id: number | null; is_active: boolean; }

export const usersAPI = {
  list: () => api.get<ManagedUser[]>('/users/'),
  misTeam: () => api.get<{ id: number; full_name: string | null; email: string; role_name: string | null }[]>('/users/mis-team'),
  performance: () => api.get<{
    summary: { total: number; closed: number; pending: number; unassigned: number };
    sla: { tracked: number; currently_overdue: number; total_breached: number; on_time_pct: number | null };
    officers: { id: number; full_name: string | null; email: string; role_name: string | null; total: number; completed: number; pending: number; in_progress: number; overdue: number }[];
    dept_managers: { id: number; full_name: string | null; email: string; total: number; pending: number; closed: number }[];
  }>('/users/performance'),
  sla: () => api.get<{
    summary: { total_tracked: number; currently_overdue: number; total_breached: number; active_with_sla: number };
    overdue_tickets: { id: number; title: string; priority: string; status: string | null; sla_deadline: string; hours_overdue: number; assigned_to: string | null; department_id: number | null; created_at: string }[];
    by_request_type: { request_type_id: number; request_type_name: string; sla_hours: number; total: number; resolved: number; on_time: number; breached: number; currently_overdue: number; on_time_pct: number | null }[];
    by_priority: { priority: string; total: number; breached: number; on_time: number; overdue: number }[];
  }>('/users/sla'),
  roles: () => api.get<ManagedRole[]>('/users/roles'),
  create: (data: { email: string; password: string; full_name: string; role_id: number | null; department_id: number | null }) => api.post<ManagedUser>('/users/', data),
  update: (id: number, data: { full_name?: string; role_id?: number | null; department_id?: number | null; is_active?: boolean; password?: string }) => api.patch<ManagedUser>(`/users/${id}`, data),
  createRole: (data: { name: string; permissions: string[]; role_type: 'Manager' | 'Officer' }) => api.post<ManagedRole>('/users/roles', data),
  departments: () => api.get<ManagedDepartment[]>('/users/departments'),
  createDepartment: (data: { name: string; manager_id: number | null }) => api.post<ManagedDepartment>('/users/departments', data),
  updateDepartment: (id: number, data: { name?: string; manager_id?: number | null }) => api.patch<ManagedDepartment>(`/users/departments/${id}`, data),
};
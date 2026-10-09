import api from './index';

export interface Schedule {
  id:                    number;
  owner_id:              number;
  owner_name:            string | null;
  title:                 string;
  description:           string | null;
  request_type_id:       number;
  request_type_name:     string | null;
  priority:              'low' | 'medium' | 'high' | 'urgent';
  due_in_hours:          number;
  preferred_officer_id:  number | null;
  preferred_officer_name:string | null;
  completion_mode:       'require_feedback' | 'auto_close';
  frequency:             'daily' | 'weekly' | 'biweekly' | 'monthly';
  hour:                  number;
  minute:                number;
  day_of_week:           number | null;   // 0=Mon … 6=Sun
  day_of_month:          number | null;   // 1–28
  is_active:             boolean;
  last_fired_at:         string | null;
  next_run_at:           string | null;
  total_fired:           number;
  created_at:            string;
  updated_at:            string | null;
}

export interface ScheduleCreate {
  title:                 string;
  description?:          string;
  request_type_id:       number;
  priority:              string;
  due_in_hours:          number;
  preferred_officer_id?: number | null;
  completion_mode:       string;
  frequency:             string;
  hour:                  number;
  minute:                number;
  day_of_week?:          number | null;
  day_of_month?:         number | null;
}

export const schedulesAPI = {
  list:   (activeOnly = false) =>
    api.get<Schedule[]>('/schedules/', { params: { active_only: activeOnly } }),

  get:    (id: number) =>
    api.get<Schedule>(`/schedules/${id}`),

  create: (data: ScheduleCreate) =>
    api.post<Schedule>('/schedules/', data),

  update: (id: number, data: Partial<ScheduleCreate>) =>
    api.patch<Schedule>(`/schedules/${id}`, data),

  delete: (id: number) =>
    api.delete(`/schedules/${id}`),

  pause:  (id: number) =>
    api.post<Schedule>(`/schedules/${id}/pause`),

  resume: (id: number) =>
    api.post<Schedule>(`/schedules/${id}/resume`),

  fireNow: (id: number) =>
    api.post<{ schedule_id: number; ticket_id: number; message: string }>(
      `/schedules/${id}/fire`
    ),
};

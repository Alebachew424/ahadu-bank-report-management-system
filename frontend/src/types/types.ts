export interface ReportRequest {
  id: number;
  title: string;
  description: string | null;
  request_type_id: number;
  status_id: number;
  /** Human-readable status name returned by the API */
  status_name?: string | null;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  due_date: string;
  additional_data: Record<string, unknown>;
  requester_id: number;
  department_id: number | null;
  assigned_to_id: number | null;
  created_at: string;
  updated_at: string | null;
  // SLA fields
  sla_deadline: string | null;
  sla_breached: boolean;
  sla_hours_remaining: number | null;   // negative = overdue
  sla_overdue: boolean;
  escalated_at: string | null;
  // AI / ML fields
  ai_suggested_type_id:    number | null;
  ai_type_confidence:      number | null;
  ai_suggested_officer_id: number | null;
  ai_officer_score:        number | null;
  ai_anomaly_flagged:      boolean;
  ai_anomaly_details:      { type: string; severity: 'low' | 'medium' | 'high'; message: string }[] | null;
}

export interface RequestCreate {
  title: string;
  description?: string;
  request_type_id: number;
  priority: 'low' | 'medium' | 'high' | 'urgent';
  due_date: string;
  additional_data?: Record<string, unknown>;
}

export type RequestUpdate = Partial<Omit<RequestCreate, 'request_type_id'>>;

/**
 * Workflow status names — mirrors the backend seed data exactly.
 */
export type WorkflowStatus =
  | 'Pending Dept Approval'
  | 'Submitted'
  | 'Assigned'
  | 'In Progress'
  | 'Needs Clarification'
  | 'Resolved'
  | 'Closed'
  | 'Rejected'
  | 'Cancelled';

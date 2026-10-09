import api from './index';

export interface AiCategorySuggestion {
  request_type_id: number;
  name:            string;
  confidence:      number;   // 0.0–1.0
  reason:          string;
}

export interface AiAnalystSuggestion {
  officer_id:      number;
  name:            string;
  email:           string;
  score:           number;
  open_tickets:    number;
  avg_rating:      number | null;
  expertise_match: number;
  reason:          string;
}

export interface AiAnomaly {
  type:     string;
  severity: 'low' | 'medium' | 'high';
  message:  string;
}

export interface AiAnalysis {
  categorisation: {
    suggestions: AiCategorySuggestion[];
    method:      'tfidf' | 'keyword' | 'none';
  };
  analyst_suggestion: {
    suggestions: AiAnalystSuggestion[];
  };
  anomalies: {
    anomalies: AiAnomaly[];
    flagged:   boolean;
  };
}

export const aiAPI = {
  /** Run full AI analysis on a draft ticket (before saving). */
  analyse: (data: {
    title:            string;
    description?:     string | null;
    priority:         string;
    request_type_id?: number | null;
  }) => api.post<AiAnalysis>('/admin/ai/analyse', data),

  /** Get ranked analyst suggestions for a specific request type + priority. */
  analystSuggestion: (request_type_id: number, priority: string) =>
    api.get<{ suggestions: AiAnalystSuggestion[] }>('/admin/ai/analyst-suggestion', {
      params: { request_type_id, priority },
    }),

  /** Get all anomaly-flagged tickets in the last N days (MIS Manager / Admin). */
  anomalyReport: (days = 7) =>
    api.get<{
      total:   number;
      days:    number;
      tickets: {
        id:              number;
        title:           string;
        requester_id:    number;
        priority:        string;
        status:          string | null;
        created_at:      string;
        anomaly_details: AiAnomaly[];
      }[];
    }>('/admin/ai/anomaly-report', { params: { days } }),
};

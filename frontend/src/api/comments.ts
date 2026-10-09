import api from './index';

export interface TicketComment {
  id: number;
  request_id: number;
  author_id: number;
  body: string;
  is_internal: boolean;
  created_at: string;
}

export const commentsAPI = {
  list: (requestId: number) => api.get<TicketComment[]>(`/requests/${requestId}/comments`),
  create: (requestId: number, body: string, isInternal = false) =>
    api.post<TicketComment>(`/requests/${requestId}/comments`, { body, is_internal: isInternal }),
};
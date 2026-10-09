import api from './index';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

export const attachmentsAPI = {
  upload: (requestId: number, file: File, isFinal: boolean = false) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('is_final', String(isFinal));
    return api.post(`/requests/${requestId}/attachments`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  list: (requestId: number) => api.get(`/requests/${requestId}/attachments`),
  download: (attachmentId: number) =>
    api.get(`/requests/attachments/${attachmentId}/download`, { responseType: 'blob' }),
  delete: (attachmentId: number) =>
    api.delete(`/requests/attachments/${attachmentId}`),
  markFinal: (attachmentId: number) =>
    api.put(`/requests/attachments/${attachmentId}/final`),
  /** Issue a short-lived token for unauthenticated preview (Google Docs Viewer) */
  previewToken: (attachmentId: number) =>
    api.post<{ token: string; expires_in: number }>(
      `/requests/attachments/${attachmentId}/preview-token`,
    ),
  /** Build the public preview URL from a token (no auth needed) */
  previewUrl: (token: string) =>
    `${API_BASE}/requests/attachments/preview/${token}`,
};

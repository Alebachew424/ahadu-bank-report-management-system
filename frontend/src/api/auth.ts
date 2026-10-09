import api from './index';

export interface LoginData {
  email: string;
  password: string;
}

export interface RegisterData {
  email: string;
  password: string;
  full_name: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export const authAPI = {
  me: () => api.get<{ id: number; email: string; full_name: string | null; role_id: number | null; role_name: string; role_type: 'Manager' | 'Officer'; permissions: string[]; is_active: boolean; is_superuser: boolean }>('/auth/me'),
  login: (data: LoginData) => api.post<AuthResponse>('/auth/login', data),
  register: (data: RegisterData) => api.post('/auth/register', data),
};

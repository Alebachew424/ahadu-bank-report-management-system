import { useState } from 'react';
import { authAPI } from '../api/auth';
import type { LoginData, RegisterData } from '../api/auth';
import type { User } from '../types/user';

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading] = useState(false);
  const [token, setToken] = useState<string | null>(localStorage.getItem('access_token'));

  const login = async (data: LoginData) => {
    const response = await authAPI.login(data);
    localStorage.setItem('access_token', response.data.access_token);
    setToken(response.data.access_token);
  };

  const register = async (data: RegisterData) => {
    await authAPI.register(data);
  };

  const logout = () => {
    localStorage.removeItem('access_token');
    setToken(null);
    setUser(null);
  };

  return { user, loading, login, register, logout, token };
}

import { create } from 'zustand';
import { api, setToken, clearToken, getToken } from '../api/client';

interface AuthState {
  authenticated: boolean;
  loading: boolean;
  error: string | null;
  login: (password: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  authenticated: !!getToken(),
  loading: false,
  error: null,

  login: async (password: string) => {
    set({ loading: true, error: null });
    try {
      const { token } = await api.login(password);
      setToken(token);
      set({ authenticated: true, loading: false });
    } catch (e: any) {
      set({ error: e.message || 'Login failed', loading: false });
    }
  },

  logout: () => {
    clearToken();
    set({ authenticated: false });
  },

  checkAuth: async () => {
    if (!getToken()) {
      set({ authenticated: false });
      return;
    }
    try {
      await api.checkAuth();
      set({ authenticated: true });
    } catch {
      clearToken();
      set({ authenticated: false });
    }
  },
}));

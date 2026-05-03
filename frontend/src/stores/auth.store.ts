import { create } from 'zustand';
import { apiClient } from '../lib/axios';
import { useTenantStore } from './tenant.store';

export type Role = 'platform_admin' | 'ngo_admin' | 'coordinator' | 'field_worker' | 'funder_readonly';

export interface AuthPayload {
  jwt: string;
  user_id: string;
  display_name?: string;
  role: Role;
  tenant_id: string;
}

interface AuthState {
  jwt: string | null;
  user_id: string | null;
  display_name: string | null;
  role: Role | null;
  language: 'en' | 'hi' | 'mr' | 'ta';
  isLoading: boolean;
  error: string | null;
  setAuth: (payload: AuthPayload) => void;
  clearAuth: () => void;
  setRole: (role: Role) => void;
  setLanguage: (lang: 'en' | 'hi' | 'mr' | 'ta') => void;
  login: (email: string, password: string) => Promise<boolean>;
  refresh: () => Promise<boolean>;
  logout: () => Promise<void>;
}

/**
 * Normalise the token field. Registry service returns `jwt`,
 * dedicated auth service returns `access_token`.
 */
function extractToken(data: any): string {
  return data?.jwt ?? data?.access_token ?? '';
}

export const useAuthStore = create<AuthState>((set, get) => ({
  // JWT lives only in memory — never written to localStorage/sessionStorage
  jwt: null,
  user_id: null,
  display_name: null,
  role: null,
  language: 'en',
  isLoading: false,
  error: null,

  setAuth: (payload) => {
    set({
      jwt: payload.jwt,
      user_id: payload.user_id,
      display_name: payload.display_name ?? null,
      role: payload.role,
      error: null,
    });
    if (payload.tenant_id) {
      // Set the tenant context (ID and Name)
      useTenantStore.getState().setTenant(payload.tenant_id, '', payload.tenant_name || '');
    }
  },

  clearAuth: () => {
    set({ jwt: null, user_id: null, display_name: null, role: null, error: null });
    useTenantStore.getState().clearTenant();
  },

  setRole: (role) => set({ role }),
  setLanguage: (language) => set({ language }),

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const tenant_slug = useTenantStore.getState().tenant_slug;
      // Call registry auth (single source of truth for login)
      const response = await apiClient.post('/proxy/auth/login', {
        email,
        password,
        ...(tenant_slug ? { tenant_slug } : {}),
      });
      const data = response.data;
      get().setAuth({
        jwt: extractToken(data),
        user_id: data.user_id,
        display_name: data.display_name ?? undefined,
        role: data.role,
        tenant_id: data.tenant_id,
      });
      set({ isLoading: false });
      return true;
    } catch (error: any) {
      let errorMessage = 'Login failed';
      if (error.response?.data?.detail) {
        errorMessage = Array.isArray(error.response.data.detail)
          ? error.response.data.detail[0].msg
          : error.response.data.detail;
      }
      set({ isLoading: false, error: errorMessage });
      return false;
    }
  },

  refresh: async () => {
    try {
      // M6: Guard URL so the interceptor never re-triggers a refresh on a failing refresh call
      const response = await apiClient.post('/proxy/auth/refresh', null, {
        _skipRefreshRetry: true,
      } as any);
      const data = response.data;
      get().setAuth({
        jwt: extractToken(data),
        user_id: data.user_id,
        display_name: data.display_name ?? undefined,
        role: data.role,
        tenant_id: data.tenant_id,
      });
      return true;
    } catch {
      get().clearAuth();
      return false;
    }
  },

  logout: async () => {
    try {
      await apiClient.post('/proxy/auth/logout');
    } finally {
      get().clearAuth();
    }
  },
}));

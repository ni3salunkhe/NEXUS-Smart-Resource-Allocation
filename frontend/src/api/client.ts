import axios from 'axios';
import { useAuthStore } from '../stores/auth.store';
import { useTenantStore } from '../stores/tenant.store';
import { errorLogger } from '../lib/errorLogger';

export const apiClient = axios.create({
  baseURL: '',
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Request interceptor: inject auth, tenant, correlation-id, language
apiClient.interceptors.request.use((config) => {
  const authState = useAuthStore.getState();
  const jwt = authState.jwt;
  const language = authState.language;

  if (jwt) {
    config.headers.Authorization = `Bearer ${jwt}`;
  }

  // Tenant ID from tenant store (persisted)
  const tenantId = useTenantStore.getState().tenant_id;
  if (tenantId) {
    config.headers['X-Tenant-ID'] = tenantId;
  }

  // Correlation ID for tracing
  config.headers['X-Correlation-ID'] = crypto.randomUUID();

  // Language header
  if (language) {
    config.headers['Accept-Language'] = language;
  }

  return config;
});

// Response interceptor: auto-refresh on 401
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const { clearAuth } = useAuthStore.getState();
        // Try refresh via proxy
        const response = await axios.post('/proxy/auth/refresh', {}, { withCredentials: true });
        const newJwt = response.data.access_token;
        useAuthStore.setState({ jwt: newJwt });
        originalRequest.headers.Authorization = `Bearer ${newJwt}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        useAuthStore.getState().clearAuth();
        window.location.href = '/auth/signin';
        return Promise.reject(refreshError);
      }
    }
    if (error.response) {
      // Server responded with non-2xx
      errorLogger.log({
        message: `API Error [${error.response.status}] ${originalRequest.method?.toUpperCase()} ${originalRequest.url}`,
        level: error.response.status >= 500 ? 'ERROR' : 'WARN',
        stack: JSON.stringify(error.response.data),
      });
    } else if (error.request) {
      // Request sent but no response
      errorLogger.log({
        message: `API Network Error: ${originalRequest.method?.toUpperCase()} ${originalRequest.url}`,
        level: 'ERROR',
      });
    }

    return Promise.reject(error);
  }
);

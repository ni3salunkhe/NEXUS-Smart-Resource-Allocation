import { create } from 'zustand';
import { io, Socket } from 'socket.io-client';
import { useAuthStore } from './auth.store';
import { useTenantStore } from './tenant.store';

interface SocketStore {
  socket: Socket | null;
  connected: boolean;
  connect: () => void;
  disconnect: () => void;
}

export const useSocketStore = create<SocketStore>((set, get) => ({
  socket: null,
  connected: false,

  connect: () => {
    if (get().socket?.connected) return;
    
    const { jwt } = useAuthStore.getState();
    const { tenant_id } = useTenantStore.getState();
    
    if (!jwt || !tenant_id) return;

    try {
      const socket = io(import.meta.env.VITE_WS_URL || window.location.origin, {
        auth: { token: jwt, tenantId: tenant_id },
        transports: ['websocket'],
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 5000,
        timeout: 10000,
      });

      socket.on('connect', () => {
        set({ connected: true });
      });

      socket.on('disconnect', () => {
        set({ connected: false });
      });

      set({ socket });
    } catch (err) {
      console.warn('WebSocket connection failed:', err);
      set({ connected: false });
    }
  },

  disconnect: () => {
    const { socket } = get();
    if (socket) {
      socket.disconnect();
      set({ socket: null, connected: false });
    }
  },
}));

import { create } from 'zustand';

interface SyncStore {
  isOnline: boolean;
  pendingSyncCount: number;
  setOnline: (status: boolean) => void;
  setPendingSyncCount: (count: number) => void;
}

export const useSyncStore = create<SyncStore>((set) => ({
  isOnline: typeof navigator !== 'undefined' ? navigator.onLine : true,
  pendingSyncCount: 0,
  setOnline: (status) => set({ isOnline: status }),
  setPendingSyncCount: (count) => set({ pendingSyncCount: count }),
}));

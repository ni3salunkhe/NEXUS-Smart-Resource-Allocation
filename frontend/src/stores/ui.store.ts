import { create } from 'zustand';

interface UiStore {
  sidebarOpen: boolean;
  activePanel: 'none' | 'household_details' | 'need_details' | 'task_dispatch' | 'volunteer_profile';
  panelReferenceId: string | null;
  emergencyMode: boolean;
  toggleSidebar: () => void;
  toggleEmergencyMode: () => void;
  openPanel: (panel: 'none' | 'household_details' | 'need_details' | 'task_dispatch' | 'volunteer_profile', id?: string) => void;
  closePanel: () => void;
}

export const useUiStore = create<UiStore>((set) => ({
  sidebarOpen: true,
  activePanel: 'none',
  panelReferenceId: null,
  emergencyMode: false,
  
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  
  toggleEmergencyMode: () => set((state) => ({ emergencyMode: !state.emergencyMode })),
  
  openPanel: (panel, id = null) => set({ activePanel: panel, panelReferenceId: id }),
  
  closePanel: () => set({ activePanel: 'none', panelReferenceId: null }),
}));

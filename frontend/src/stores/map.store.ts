import { create } from 'zustand';
import { NeedCategory } from '../types/need.types';

interface MapStore {
  active_ward_id: string | null;
  selected_layers: ('needs' | 'volunteers' | 'households' | 'task_routes')[];
  urgency_filter_min: number;
  category_filter: NeedCategory[];
  volunteer_positions: Record<string, { lat: number; lng: number; updated_at: string }>;
  pulsing_markers: string[];

  setActiveWard: (ward_id: string | null) => void;
  toggleLayer: (layer: 'needs' | 'volunteers' | 'households' | 'task_routes') => void;
  setUrgencyFilter: (min: number) => void;
  updateVolunteerPosition: (id: string, pos: { lat: number; lng: number }) => void;
  addPulsingMarker: (need_id: string) => void;
}

export const useMapStore = create<MapStore>((set) => ({
  active_ward_id: null,
  selected_layers: ['needs', 'volunteers'],
  urgency_filter_min: 0,
  category_filter: [],
  volunteer_positions: {},
  pulsing_markers: [],

  setActiveWard: (ward_id) => set({ active_ward_id: ward_id }),
  
  toggleLayer: (layer) =>
    set((state) => ({
      selected_layers: state.selected_layers.includes(layer)
        ? state.selected_layers.filter((l) => l !== layer)
        : [...state.selected_layers, layer],
    })),
    
  setUrgencyFilter: (min) => set({ urgency_filter_min: min }),
  
  updateVolunteerPosition: (id, pos) =>
    set((state) => ({
      volunteer_positions: {
        ...state.volunteer_positions,
        [id]: { ...pos, updated_at: new Date().toISOString() },
      },
    })),
    
  addPulsingMarker: (need_id) =>
    set((state) => ({
      pulsing_markers: [...new Set([...state.pulsing_markers, need_id])],
    })),
}));

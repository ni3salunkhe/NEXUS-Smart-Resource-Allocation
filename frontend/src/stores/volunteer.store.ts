import { create } from 'zustand';
import { VolunteerAPI } from '../api/endpoints';

export interface Volunteer {
  volunteer_id: string;
  tenant_id?: string;
  user_id?: string;
  skills: string[];
  preferred_language?: string[];
  active: boolean;
  verified?: boolean;
  max_distance_km: number;
  total_deployments: number;
  outcome_rating?: number;
  burnout_risk_score: number;
  ward_id?: string;
  is_available_now?: boolean;
  preferred_channel?: string;
  display_name?: string;
  created_at?: string;
}

interface VolunteerStore {
  volunteers: Volunteer[];
  isLoading: boolean;
  error: string | null;
  fetchVolunteers: (params?: any) => Promise<void>;
  setVolunteers: (volunteers: Volunteer[]) => void;
}

export const useVolunteerStore = create<VolunteerStore>((set) => ({
  volunteers: [],
  isLoading: false,
  error: null,

  fetchVolunteers: async (params?: any) => {
    set({ isLoading: true, error: null });
    try {
      const res = await VolunteerAPI.list(params);
      set({ volunteers: res.data, isLoading: false });
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Failed to fetch volunteers';
      set({ error: msg, isLoading: false });
      console.error('fetchVolunteers error:', msg);
    }
  },

  setVolunteers: (volunteers) => set({ volunteers }),
}));

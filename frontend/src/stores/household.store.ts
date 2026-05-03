import { create } from 'zustand';
import { HouseholdAPI } from '../api/endpoints';
import { useAuthStore } from './auth.store';
import { toast } from 'react-hot-toast';

export interface MemberRow {
  id: string;
  name: string;
  role: string;
  age: 'infant' | 'child' | 'youth' | 'adult' | 'elderly';
  gender: string;
  vulnerability: {
    disabled: boolean;
    chronic_illness: boolean;
    pregnant: boolean;
  };
}

export interface Household {
  household_id: string;
  display_name?: string;
  tenant_id?: string;
  ward_id?: string;
  total_members: number;
  location_description: string;
  status: 'active' | 'relocated' | 'dissolved' | 'merged_away' | 'opted_out';
  vulnerability_score: number;
  vulnerability_flags?: Record<string, boolean>;
  location?: { lat: number; lng: number } | null;
  location_confidence?: number;
  landmark_tags?: string[];
  dwelling_type?: string;
  economic_tier?: string;
  total_needs_reported?: number;
  total_tasks_completed?: number;
  last_need_reported_at?: string;
  last_assistance_at?: string;
  total_assistance_value?: number;
  assistance_categories?: string[];
  crisis_frequency?: number;
  data_quality_score?: number;
  created_at?: string;
  updated_at?: string;
  members?: MemberRow[];
}

interface HouseholdStore {
  households: Household[];
  isLoading: boolean;
  error: string | null;
  fetchHouseholds: (params?: any) => Promise<void>;
  addHousehold: (data: any) => Promise<void>;
  updateHousehold: (id: string, updates: Partial<Household>) => Promise<void>;
  deleteHousehold: (id: string) => void;
  getHousehold: (id: string) => Household | undefined;
  searchHouseholds: (query: string) => Promise<void>;
}

export const useHouseholdStore = create<HouseholdStore>((set, get) => ({
  households: [],
  isLoading: false,
  error: null,

  fetchHouseholds: async (params?: any) => {
    set({ isLoading: true, error: null });
    try {
      const res = await HouseholdAPI.list(params);
      set({ households: res.data, isLoading: false });
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Failed to fetch households';
      set({ error: msg, isLoading: false });
      console.error('fetchHouseholds error:', msg);
    }
  },

  searchHouseholds: async (query: string) => {
    if (!query) return get().fetchHouseholds();
    set({ isLoading: true, error: null });
    try {
      const res = await HouseholdAPI.search({ query });
      set({ households: res.data, isLoading: false });
    } catch (err: any) {
      const msg = err?.response?.data?.detail || 'Failed to search households';
      set({ error: msg, isLoading: false });
    }
  },
  
  addHousehold: async (data: any) => {
    try {
      const res = await HouseholdAPI.create(data);
      // Refetch to get full record from server
      await get().fetchHouseholds();
      toast.success(`Household ${res.data.household_id} created`);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to create household');
    }
  },
  
  updateHousehold: async (id, updates) => {
    // Optimistic update
    set((state) => ({
      households: state.households.map((h) =>
        h.household_id === id ? { ...h, ...updates } : h
      )
    }));
    try {
      await HouseholdAPI.update(id, updates);
    } catch (err: any) {
      toast.error('Failed to update household');
      // Revert by refetching
      await get().fetchHouseholds();
    }
  },
  
  deleteHousehold: (id) => {
    // Soft delete from UI only (backend uses status change, not DELETE)
    set((state) => ({
      households: state.households.filter((h) => h.household_id !== id)
    }));
  },
  
  getHousehold: (id) => get().households.find((h) => h.household_id === id),
}));

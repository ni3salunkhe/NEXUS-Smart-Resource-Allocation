import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface TenantStore {
  tenant_id: string | null;
  tenant_slug: string | null;
  tenant_name: string | null;
  setTenant: (id: string, slug: string, name: string) => void;
  clearTenant: () => void;
}

export const useTenantStore = create<TenantStore>()(
  persist(
    (set) => ({
      tenant_id: null,
      tenant_slug: null,
      tenant_name: null,
      setTenant: (id, slug, name) => set({ tenant_id: id, tenant_slug: slug, tenant_name: name }),
      clearTenant: () => set({ tenant_id: null, tenant_slug: null, tenant_name: null }),
    }),
    {
      name: 'nexus-tenant-storage',
    }
  )
);

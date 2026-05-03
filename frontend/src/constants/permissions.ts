export type UserRole = 'platform_admin' | 'ngo_admin' | 'coordinator' | 'field_worker' | 'funder_readonly' | 'volunteer';

export const ROLE_PERMISSIONS: Record<UserRole, string[]> = {
  platform_admin: ['overview', 'needs', 'tasks', 'map', 'volunteers', 'households', 'inbox', 'reports', 'settings', 'tenants', 'field'],
  ngo_admin: ['overview', 'needs', 'tasks', 'map', 'volunteers', 'households', 'inbox', 'reports', 'settings', 'field'],
  coordinator: ['overview', 'needs', 'tasks', 'map', 'volunteers', 'households', 'inbox', 'field'],
  field_worker: ['overview', 'tasks', 'map', 'households', 'inbox', 'field'],
  funder_readonly: ['overview', 'map', 'households'],
  volunteer: ['overview', 'households', 'inbox'],
};

export function hasPermission(role: UserRole | null | undefined, feature: string): boolean {
  if (!role) return false;
  return ROLE_PERMISSIONS[role]?.includes(feature) || false;
}

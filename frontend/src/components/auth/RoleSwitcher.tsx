import React from 'react';
import { useAuthStore } from '../../stores/auth.store';
import { ShieldCheck, ChevronDown } from 'lucide-react';
import { cn } from '../../lib/utils';

const ROLES = [
  { id: 'super_admin', label: 'Super Admin' },
  { id: 'org_admin', label: 'Org Admin' },
  { id: 'coordinator', label: 'Coordinator' },
  { id: 'field_worker', label: 'Field Worker' },
  { id: 'volunteer', label: 'Volunteer' },
  { id: 'read_only', label: 'Read Only' },
];

export function RoleSwitcher({ minimized }: { minimized?: boolean }) {
  const { role, setRole } = useAuthStore();
  const currentRole = ROLES.find(r => r.id === role);

  return (
    <div className={cn("px-4 py-3 rounded-2xl bg-brand-800/50 border border-brand-700/50", minimized ? "mx-1" : "mx-2")}>
      {!minimized ? (
        <>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-bold text-brand-300 uppercase tracking-widest">Protocol Mask</span>
            <ShieldCheck className="w-3 h-3 text-brand-400" />
          </div>
          <select 
            value={role || ''} 
            onChange={(e) => setRole(e.target.value as any)}
            className="w-full bg-brand-900 border border-brand-700 text-brand-50 text-[10px] font-bold px-2 py-1.5 rounded-lg outline-none focus:border-brand-400 transition-colors uppercase tracking-wider"
          >
            {ROLES.map(r => (
              <option key={r.id} value={r.id}>{r.label}</option>
            ))}
          </select>
        </>
      ) : (
        <div className="flex justify-center group relative cursor-pointer">
           <ShieldCheck className="w-5 h-5 text-brand-400" />
           <div className="absolute left-full ml-4 top-0 bg-brand-900 border border-brand-700 rounded-xl p-2 hidden group-hover:block z-50 shadow-2xl min-w-[120px]">
              {ROLES.map(r => (
                <button 
                  key={r.id} 
                  onClick={() => setRole(r.id as any)}
                  className={cn(
                    "w-full text-left px-2 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-colors",
                    role === r.id ? "bg-brand-600 text-white" : "text-brand-300 hover:text-white"
                  )}
                >
                  {r.label}
                </button>
              ))}
           </div>
        </div>
      )}
    </div>
  );
}

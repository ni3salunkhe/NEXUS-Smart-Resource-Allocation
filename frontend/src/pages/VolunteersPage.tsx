import React, { useState, useEffect } from 'react';
import { useUiStore } from '../stores/ui.store';
import { useVolunteerStore } from '../stores/volunteer.store';
import { Search, UserCheck, ShieldAlert, Award, FileText, Loader2, UserPlus } from 'lucide-react';
import { TaskDispatchModal } from '../components/operations/TaskDispatchModal';
import { useNavigate } from 'react-router-dom';

export function VolunteersPage() {
  const navigate = useNavigate();
  const { activePanel, panelReferenceId } = useUiStore();
  const { volunteers, isLoading, fetchVolunteers } = useVolunteerStore();
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    fetchVolunteers();
  }, []);

  const filtered = volunteers.filter(v => {
    if (!searchTerm) return true;
    const q = searchTerm.toLowerCase();
    return (
      v.volunteer_id.toLowerCase().includes(q) ||
      (v.display_name || '').toLowerCase().includes(q) ||
      v.skills.some(s => s.toLowerCase().includes(q))
    );
  });

  return (
    <div className="flex flex-col h-full">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-headline font-semibold text-brand-900">Volunteer Directory</h2>
          <p className="text-sm text-gray-500 mt-1">Manage field teams and monitor their status.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex bg-white border border-warm-border rounded-xl overflow-hidden relative max-w-xs w-full shadow-sm">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input 
              type="text" 
              placeholder="Search volunteers or skills..." 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-9 pr-4 py-2 text-sm w-full focus:outline-none"
            />
          </div>
          <button 
            onClick={() => navigate('/volunteers/register')}
            className="flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded-xl text-sm font-bold shadow-sm hover:bg-green-700 transition-all"
          >
            <UserPlus className="w-4 h-4" /> Register Volunteer
          </button>
          <button 
            onClick={() => navigate('/households/intake')}
            className="flex items-center gap-2 bg-brand-600 text-white px-4 py-2 rounded-xl text-sm font-bold shadow-sm hover:bg-brand-800 transition-all"
          >
            <FileText className="w-4 h-4" /> Start Intake
          </button>
        </div>
      </div>

      {isLoading && volunteers.length === 0 ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 text-brand-600 animate-spin" />
          <span className="ml-3 text-gray-500">Loading volunteers...</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map(vol => (
            <div key={vol.volunteer_id} className="bg-white p-6 rounded-3xl border border-warm-border hover:border-brand-400 transition-all shadow-sm">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-brand-100 flex items-center justify-center text-brand-600 font-bold border border-brand-200">
                    {(vol.display_name || vol.volunteer_id).charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <h3 className="font-bold text-gray-900 text-sm">{vol.display_name || `Vol-${vol.volunteer_id.slice(0, 6)}`}</h3>
                    <span className="text-xs text-gray-500 font-mono tracking-tighter">{vol.volunteer_id.slice(0, 10)}</span>
                  </div>
                </div>
                {vol.active ? (
                  <span className="w-2.5 h-2.5 rounded-full bg-urgency-low ring-4 ring-urgency-low/20"></span>
                ) : (
                  <span className="w-2.5 h-2.5 rounded-full bg-gray-300"></span>
                )}
              </div>

              <div className="flex flex-wrap gap-1.5 mb-4">
                  {vol.skills.map(skill => (
                    <span key={skill} className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px] uppercase font-semibold tracking-wider">
                      {skill.replace(/_/g, ' ')}
                    </span>
                  ))}
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs border-t border-warm-border/50 pt-3 mt-auto">
                <div className="flex flex-col">
                  <span className="text-gray-400 font-semibold uppercase tracking-widest text-[10px]">Max Dist</span>
                  <span className="font-medium mt-0.5">{vol.max_distance_km} km</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-gray-400 font-semibold uppercase tracking-widest text-[10px]">Deployments</span>
                  <span className="font-medium flex items-center gap-1 mt-0.5"><Award className="w-3 h-3 text-brand-400" /> {vol.total_deployments}</span>
                </div>
              </div>

              {vol.burnout_risk_score > 0.7 && (
                <div className="mt-3 bg-red-50 border border-red-100 p-2 rounded flex items-start gap-2">
                  <ShieldAlert className="w-4 h-4 text-red-600 flex-shrink-0" />
                  <span className="text-[10px] text-red-700 font-medium leading-tight pt-0.5">
                    High burnout risk ({Math.round(vol.burnout_risk_score * 100)}%). Rest advised.
                  </span>
                </div>
              )}
              
            </div>
          ))}
          {filtered.length === 0 && !isLoading && (
            <div className="col-span-full text-center py-16 text-gray-400">
              <UserCheck className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="font-medium">No volunteers found</p>
            </div>
          )}
        </div>
      )}

      {activePanel === 'task_dispatch' && panelReferenceId && (
        <TaskDispatchModal taskId={panelReferenceId} />
      )}
    </div>
  );
}

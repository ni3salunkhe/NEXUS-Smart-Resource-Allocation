import React, { useState, useEffect } from 'react';
import { useUiStore } from '../stores/ui.store';
import { NeedsList } from '../components/needs/NeedsList';
import { NeedDetailDrawer } from '../components/needs/NeedDetailDrawer';
import { Filter, SlidersHorizontal, ArrowDownWideNarrow } from 'lucide-react';
import { NeedAPI } from '../api/endpoints';

export function NeedsTriagePage() {
  const { activePanel, panelReferenceId } = useUiStore();
  const [filterSeverity, setFilterSeverity] = useState<number>(0);
  const [filterCategory, setFilterCategory] = useState<string>('all');
  const [stats, setStats] = useState([
    { label: 'Unverified Needs', count: '...', color: 'text-urgency-high', bg: 'bg-urgency-high/10' },
    { label: 'Critical Escalations', count: '...', color: 'text-urgency-critical', bg: 'bg-urgency-critical/10' },
    { label: 'Assigned', count: '...', color: 'text-urgency-low', bg: 'bg-urgency-low/10' },
    { label: 'All Needs', count: '...', color: 'text-gray-600', bg: 'bg-gray-100' },
  ]);

  useEffect(() => {
    const loadStats = async () => {
      try {
        const [unverified, assigned, all] = await Promise.allSettled([
          NeedAPI.list({ status: 'unverified', limit: 100 }),
          NeedAPI.list({ status: 'assigned', limit: 100 }),
          NeedAPI.list({ limit: 100 }),
        ]);
        const uCount = unverified.status === 'fulfilled' ? unverified.value.data.length : 0;
        const aCount = assigned.status === 'fulfilled' ? assigned.value.data.length : 0;
        const tCount = all.status === 'fulfilled' ? all.value.data.length : 0;
        const critCount = all.status === 'fulfilled' 
          ? all.value.data.filter((n: any) => n.urgency_score >= 0.8).length : 0;
        
        setStats([
          { label: 'Unverified Needs', count: String(uCount), color: 'text-urgency-high', bg: 'bg-urgency-high/10' },
          { label: 'Critical Escalations', count: String(critCount), color: 'text-urgency-critical', bg: 'bg-urgency-critical/10' },
          { label: 'Assigned', count: String(aCount), color: 'text-urgency-low', bg: 'bg-urgency-low/10' },
          { label: 'All Needs', count: String(tCount), color: 'text-gray-600', bg: 'bg-gray-100' },
        ]);
      } catch (err) {
        console.error('Failed to load triage stats:', err);
      }
    };
    loadStats();
  }, []);

  return (
    <div className="flex flex-col h-full bg-slate-50 relative">
      <div className="flex-none mb-6">
        <h2 className="text-2xl font-headline font-semibold text-brand-900 mb-4">Needs Triage</h2>
        
        {/* KPI Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
          {stats.map((stat, i) => (
            <div key={i} className="bg-white rounded-3xl p-6 shadow-sm border border-warm-border flex flex-col justify-center">
              <span className="text-sm font-medium text-gray-500">{stat.label}</span>
              <div className={`mt-2 text-2xl font-bold ${stat.color}`}>{stat.count}</div>
            </div>
          ))}
        </div>

        {/* Toolbar */}
        <div className="flex items-center justify-between bg-white p-4 rounded-2xl shadow-sm border border-warm-border mb-6">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm text-gray-600 pl-2">
              <Filter className="w-4 h-4" />
              <span className="font-medium">Filter By:</span>
            </div>
            <select 
              value={filterCategory} 
              onChange={(e) => setFilterCategory(e.target.value)}
              className="text-sm border-none bg-slate-50 rounded-xl px-3 py-1.5 focus:ring-1 focus:ring-brand-400 focus:outline-none"
            >
              <option value="all">All Categories</option>
              <option value="food">Food</option>
              <option value="health">Health</option>
              <option value="shelter">Shelter</option>
              <option value="water">WaSH</option>
            </select>
            <select 
              value={filterSeverity} 
              onChange={(e) => setFilterSeverity(Number(e.target.value))}
              className="text-sm border-none bg-slate-50 rounded-xl px-3 py-1.5 focus:ring-1 focus:ring-brand-400 focus:outline-none"
            >
              <option value={0}>Any Urgency</option>
              <option value={0.8}>Critical (0.8+)</option>
              <option value={0.6}>High (0.6+)</option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <button className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-600 hover:text-brand-600 hover:bg-brand-50 rounded-md transition-colors">
              <ArrowDownWideNarrow className="w-4 h-4" />
              Sort: Urgency
            </button>
            <button className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-600 hover:text-brand-600 hover:bg-brand-50 rounded-md transition-colors">
              <SlidersHorizontal className="w-4 h-4" />
              Advanced
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-auto min-h-0 relative">
        <NeedsList category={filterCategory} minUrgency={filterSeverity} />
      </div>

      {activePanel === 'need_details' && panelReferenceId && (
        <NeedDetailDrawer needId={panelReferenceId} />
      )}
    </div>
  );
}

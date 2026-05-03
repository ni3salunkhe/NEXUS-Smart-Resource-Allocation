import React, { useEffect, useState } from 'react';
import { StatCard } from '../components/dashboard/StatCard';
import { useHouseholdStore } from '../stores/household.store';
import { ShieldAlert, ListTodo, Users, CheckCircle, Home, TrendingUp, Loader2 } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { NeedAPI, TaskAPI, VolunteerAPI } from '../api/endpoints';

export function OverviewPage() {
  const { households, fetchHouseholds } = useHouseholdStore();
  const [stats, setStats] = useState({ needs: 0, tasks: 0, volunteers: 0 });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadAll = async () => {
      setLoading(true);
      try {
        await fetchHouseholds();
        const [needsRes, tasksRes, volsRes] = await Promise.allSettled([
          NeedAPI.list({ status: 'unverified', limit: 1 }),
          TaskAPI.list({ status: 'in_progress', limit: 1 }),
          VolunteerAPI.list({ active: true, limit: 1 }),
        ]);
        // For counts we check if data came back
        setStats({
          needs: needsRes.status === 'fulfilled' ? needsRes.value.data.length : 0,
          tasks: tasksRes.status === 'fulfilled' ? tasksRes.value.data.length : 0,
          volunteers: volsRes.status === 'fulfilled' ? volsRes.value.data.length : 0,
        });
      } catch (err) {
        console.error('Overview load error:', err);
      } finally {
        setLoading(false);
      }
    };
    loadAll();
  }, []);

  return (
    <div className="flex flex-col h-full overflow-y-auto pb-10">
      <div className="mb-6">
        <h2 className="text-2xl font-headline font-semibold text-brand-900">Operations Overview</h2>
        <p className="text-sm text-gray-500">Live summary of current field operations and active needs.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard 
          label="Unverified Needs" 
          value={loading ? '...' : String(stats.needs)} 
          icon={ShieldAlert} 
          colorClass="bg-urgency-critical/10 text-urgency-critical" 
        />
        <StatCard 
          label="Tasks In Progress" 
          value={loading ? '...' : String(stats.tasks)} 
          icon={ListTodo} 
          colorClass="bg-brand-50 text-brand-600" 
        />
        <StatCard 
          label="Active Volunteers" 
          value={loading ? '...' : String(stats.volunteers)} 
          icon={Users} 
          colorClass="bg-category-education/10 text-category-education" 
        />
        <StatCard 
          label="Households Covered" 
          value={loading ? '...' : String(households.length)} 
          icon={Home} 
          colorClass="bg-category-health/10 text-category-health" 
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* System Health */}
        <div className="bg-brand-900 rounded-3xl p-8 text-white flex flex-col justify-between shadow-xl shadow-brand-100 lg:col-span-1 min-h-[200px]">
           <div>
              <p className="text-[10px] font-bold text-brand-200 uppercase tracking-widest mb-1">System Health</p>
              <h3 className="text-2xl font-light">{loading ? 'Checking...' : 'Operational'}</h3>
           </div>
           <div className="flex items-center gap-2">
              <CheckCircle className="w-5 h-5 text-emerald-400" />
              <span className="text-sm text-brand-100">Backend services connected</span>
           </div>
        </div>

        <div className="bg-indigo-600 rounded-3xl p-8 text-white flex flex-col justify-between shadow-xl shadow-indigo-100 lg:col-span-1 min-h-[200px]">
           <div>
              <p className="text-[10px] font-bold text-indigo-200 uppercase tracking-widest mb-1">API Status</p>
              <h3 className="text-2xl font-medium mt-1">Live Integration</h3>
           </div>
           <p className="text-sm text-indigo-100 opacity-80">Registry • Ingestion • Coordination</p>
        </div>

        <div className="bg-white rounded-3xl p-8 border border-warm-border shadow-sm flex flex-col justify-between lg:col-span-1 min-h-[200px]">
           <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-indigo-600 animate-pulse"></div>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">Households in DB</p>
           </div>
           <div className="flex items-end gap-1">
              <p className="text-4xl font-bold text-slate-900">{loading ? '...' : households.length}</p>
              <span className="text-xs font-bold text-slate-400 uppercase pb-1">records</span>
           </div>
           <div className="w-full bg-slate-100 h-1 rounded-full overflow-hidden">
              <div className="w-[90%] h-full bg-indigo-600"></div>
           </div>
        </div>
      </div>
    </div>
  );
}

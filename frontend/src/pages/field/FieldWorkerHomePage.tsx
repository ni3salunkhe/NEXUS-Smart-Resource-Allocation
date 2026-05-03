import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  ClipboardList, Scan, History, Play, CheckCircle, 
  Clock, MapPin, AlertCircle, ChevronRight, User
} from 'lucide-react';
import { motion } from 'framer-motion';
import { NeedAPI, TaskAPI } from '../../api/endpoints';
import { NeedRecord } from '../../types/need.types';
import { Task } from '../../types/task.types';
import { useAuthStore } from '../../stores/auth.store';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const FieldWorkerHomePage: React.FC = () => {
  const navigate = useNavigate();
  const { user_id, display_name } = useAuthStore();
  const [recentNeeds, setRecentNeeds] = useState<NeedRecord[]>([]);
  const [activeTasks, setActiveTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [needsRes, tasksRes] = await Promise.all([
          NeedAPI.list({ limit: 5 }),
          TaskAPI.list({ limit: 5, status: 'in_progress' })
        ]);
        
        // Client-side filter for needs reported by me if backend didn't do it
        const myNeeds = needsRes.data.filter(n => n.reported_by === user_id);
        setRecentNeeds(myNeeds);
        
        // Tasks assigned to me
        const myTasks = tasksRes.data.filter(t => t.assigned_volunteer_id === user_id);
        setActiveTasks(myTasks);
      } catch (err) {
        console.error('Failed to fetch home data:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [user_id]);

  const statusColors: Record<string, string> = {
    unverified: 'bg-slate-100 text-slate-500',
    verified: 'bg-blue-100 text-blue-600',
    assigned: 'bg-amber-100 text-amber-600',
    in_progress: 'bg-orange-100 text-orange-600',
    resolved: 'bg-emerald-100 text-emerald-600',
    closed: 'bg-emerald-100 text-emerald-600',
    duplicate: 'bg-slate-100 text-slate-400',
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-black p-4 pb-24">
      {/* Header */}
      <header className="flex justify-between items-center pt-6 mb-10">
        <div className="space-y-1">
          <h1 className="text-3xl font-black text-slate-900 dark:text-white tracking-tight">NEXUS</h1>
          <div className="flex items-center gap-2 px-3 py-1 bg-white dark:bg-slate-900 rounded-full shadow-sm border border-slate-100 dark:border-slate-800">
             <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
             <span className="text-[10px] font-black uppercase text-slate-500 tracking-widest">Field Worker Active</span>
          </div>
        </div>
        <div className="w-12 h-12 bg-slate-900 dark:bg-white rounded-2xl flex items-center justify-center shadow-lg shadow-slate-900/20">
          <User className="w-6 h-6 text-white dark:text-slate-900" />
        </div>
      </header>

      <div className="space-y-8">
        {/* Main Actions */}
        <div className="grid grid-cols-1 gap-4">
          <motion.button
            whileTap={{ scale: 0.98 }}
            onClick={() => navigate('/field/report')}
            className="group relative overflow-hidden bg-blue-600 p-8 rounded-[40px] text-left shadow-2xl shadow-blue-600/30 transition-all border-b-8 border-blue-800"
          >
            <div className="absolute top-0 right-0 w-48 h-48 bg-white/10 blur-3xl -mr-16 -mt-16 group-hover:scale-110 transition-transform" />
            <div className="relative z-10 space-y-4">
              <div className="w-16 h-16 bg-white/20 rounded-3xl flex items-center justify-center backdrop-blur-md">
                <ClipboardList className="w-8 h-8 text-white" />
              </div>
              <div className="space-y-1">
                <h2 className="text-2xl font-black text-white leading-none">Report a Need</h2>
                <p className="text-white/60 text-xs font-bold uppercase tracking-widest">Starts new assessment</p>
              </div>
            </div>
          </motion.button>

          <motion.button
            whileTap={{ scale: 0.98 }}
            className="group relative overflow-hidden bg-slate-900 dark:bg-slate-800 p-8 rounded-[40px] text-left shadow-2xl transition-all border-b-8 border-slate-950"
          >
            <div className="absolute top-0 right-0 w-48 h-48 bg-blue-500/10 blur-3xl -mr-16 -mt-16 group-hover:scale-110 transition-transform" />
            <div className="relative z-10 space-y-4 flex justify-between items-end">
               <div className="space-y-4">
                  <div className="w-16 h-16 bg-white/10 rounded-3xl flex items-center justify-center backdrop-blur-md">
                    <Scan className="w-8 h-8 text-white" />
                  </div>
                  <div className="space-y-1">
                    <h2 className="text-2xl font-black text-white leading-none">Scan Survey</h2>
                    <p className="text-white/40 text-xs font-bold uppercase tracking-widest">Optical intake</p>
                  </div>
               </div>
               <div className="bg-white/10 px-4 py-2 rounded-xl backdrop-blur-md">
                  <span className="text-[10px] font-black text-white tracking-widest uppercase">Beta</span>
               </div>
            </div>
          </motion.button>

          <motion.button
            whileTap={{ scale: 0.98 }}
            onClick={() => navigate('/field/tasks')}
            className="group relative overflow-hidden bg-emerald-600 p-8 rounded-[40px] text-left shadow-2xl shadow-emerald-600/20 transition-all border-b-8 border-emerald-800"
          >
            <div className="absolute top-0 right-0 w-48 h-48 bg-white/10 blur-3xl -mr-16 -mt-16 group-hover:scale-110 transition-transform" />
            <div className="relative z-10 space-y-4 flex justify-between items-end">
               <div className="space-y-4">
                  <div className="w-16 h-16 bg-white/20 rounded-3xl flex items-center justify-center backdrop-blur-md">
                    <CheckCircle className="w-8 h-8 text-white" />
                  </div>
                  <div className="space-y-1">
                    <h2 className="text-2xl font-black text-white leading-none">My Tasks</h2>
                    <p className="text-white/60 text-xs font-bold uppercase tracking-widest">Volunteer assignments</p>
                  </div>
               </div>
               {activeTasks.length > 0 && (
                 <div className="bg-white/20 px-4 py-2 rounded-xl backdrop-blur-md">
                   <span className="text-[10px] font-black text-white tracking-widest uppercase">{activeTasks.length} Active</span>
                 </div>
               )}
            </div>
          </motion.button>
        </div>

        {/* Status Lists */}
        <div className="space-y-6">
          <div className="flex justify-between items-center px-4">
            <h3 className="text-sm font-black uppercase tracking-widest text-slate-400">My Reports</h3>
            <button className="text-[10px] font-black uppercase tracking-tight text-blue-600 flex items-center gap-1">
              View All <ChevronRight className="w-3 h-3" />
            </button>
          </div>

          <div className="space-y-3">
             {loading ? (
               [1, 2].map(i => <div key={i} className="h-24 bg-white dark:bg-slate-900 animate-pulse rounded-3xl" />)
             ) : recentNeeds.length > 0 ? (
               recentNeeds.map(need => (
                 <div key={need.need_id} className="bg-white dark:bg-slate-900 p-5 rounded-3xl shadow-sm border border-slate-100 dark:border-slate-800 flex items-center gap-4">
                   <div className="w-12 h-12 bg-slate-50 dark:bg-slate-800 rounded-2xl flex items-center justify-center shrink-0">
                     <History className="w-6 h-6 text-slate-400" />
                   </div>
                   <div className="flex-1 min-w-0">
                      <p className="text-xs font-bold text-slate-900 dark:text-white truncate uppercase tracking-tight">Need {need.need_id.slice(-6)}</p>
                      <p className="text-[10px] font-bold text-slate-400 truncate">{need.category.toUpperCase()}</p>
                   </div>
                   <span className={cn(
                     "px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-tighter shrink-0",
                     statusColors[need.status] || 'bg-slate-100'
                   )}>
                     {need.status.replace('_', ' ')}
                   </span>
                 </div>
               ))
             ) : (
               <div className="text-center py-8 bg-white dark:bg-slate-900 rounded-3xl border-2 border-dashed border-slate-100 dark:border-slate-800">
                  <p className="text-xs font-bold text-slate-400">No reports yet</p>
               </div>
             )}
          </div>
        </div>

        {activeTasks.length > 0 && (
          <div className="space-y-6">
            <h3 className="text-sm font-black uppercase tracking-widest text-slate-400 px-4">Direct Tasks</h3>
            <div className="space-y-3">
               {activeTasks.map(task => (
                 <div key={task.task_id} className="bg-orange-50 dark:bg-orange-900/20 p-5 rounded-3xl border-2 border-orange-100 dark:border-orange-900/30 flex items-center gap-4">
                   <div className="w-12 h-12 bg-orange-500 rounded-2xl flex items-center justify-center shrink-0 shadow-lg shadow-orange-500/20">
                     <Play className="w-6 h-6 text-white fill-current" />
                   </div>
                   <div className="flex-1 min-w-0">
                      <p className="text-xs font-black text-orange-700 dark:text-orange-400">ACTIVE RESPONSE</p>
                      <p className="text-[10px] font-bold text-orange-600/60 truncate">Task #{task.task_id.slice(-6)}</p>
                   </div>
                   <ChevronRight className="w-5 h-5 text-orange-500" />
                 </div>
               ))}
            </div>
          </div>
        )}
      </div>

      {/* Bottom Nav Mockup */}
      <div className="fixed bottom-0 left-0 right-0 p-4 bg-transparent pointer-events-none">
         <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-2xl px-8 py-4 rounded-[32px] border border-white/20 shadow-2xl flex justify-between items-center pointer-events-auto max-w-sm mx-auto">
            <button className="text-blue-600"><Play className="w-6 h-6 fill-current" /></button>
            <button className="text-slate-400"><History className="w-6 h-6" /></button>
            <button className="text-slate-400"><User className="w-6 h-6" /></button>
         </div>
      </div>
    </div>
  );
};

export default FieldWorkerHomePage;

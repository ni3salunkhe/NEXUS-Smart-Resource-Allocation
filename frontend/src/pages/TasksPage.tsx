import React, { useEffect, useState, useCallback, useRef } from 'react';
import { 
  CheckCircle2, 
  Clock, 
  AlertTriangle, 
  TrendingUp,
  User,
  MoreVertical,
  Loader2,
  RefreshCw,
  XCircle,
  Lock
} from 'lucide-react';
import { cn } from '../lib/utils';
import { TaskStatus } from '../types/task.types';
import { TaskAPI } from '../api/endpoints';
import { TASK_STATE_COLORS, TASK_STATE_LABELS } from '../constants/taskStates';
import type { TaskState } from '../constants/taskStates';
import { toast } from 'react-hot-toast';

const STAGES: { id: TaskState; label: string; color: string; dotColor: string }[] = [
  { id: 'unassigned', label: 'Unassigned', color: 'text-gray-600', dotColor: 'bg-gray-400' },
  { id: 'dispatched', label: 'Dispatched', color: 'text-blue-600', dotColor: 'bg-blue-500' },
  { id: 'accepted', label: 'Accepted', color: 'text-indigo-600', dotColor: 'bg-indigo-500' },
  { id: 'in_progress', label: 'In Progress', color: 'text-amber-600', dotColor: 'bg-amber-500' },
  { id: 'completed', label: 'Completed', color: 'text-emerald-600', dotColor: 'bg-emerald-500' },
  { id: 'closed', label: 'Closed', color: 'text-slate-500', dotColor: 'bg-slate-400' },
];

interface TaskRow {
  task_id: string;
  need_id: string;
  household_id?: string;
  assigned_volunteer_id?: string;
  status: string;
  created_at?: string;
  dispatched_at?: string;
  accepted_at?: string;
  started_at?: string;
  completed_at?: string;
  outcome_status?: string;
  match_score?: number;
}

export function TasksPage() {
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(Date.now());
  const prevTasksRef = useRef<string>('');

  const fetchTasks = useCallback(async () => {
    try {
      const res = await TaskAPI.list({ limit: 100 });
      const newTasks = Array.isArray(res.data) ? res.data : res.data?.items || [];
      
      // Detect changes for visual feedback
      const newHash = JSON.stringify(newTasks.map((t: TaskRow) => `${t.task_id}:${t.status}`));
      if (prevTasksRef.current && prevTasksRef.current !== newHash) {
        // Tasks changed — show subtle notification
        const oldStatuses = new Map(
          tasks.map(t => [t.task_id, t.status])
        );
        newTasks.forEach((t: TaskRow) => {
          const old = oldStatuses.get(t.task_id);
          if (old && old !== t.status) {
            toast(`Task ${t.task_id.slice(-6)} → ${TASK_STATE_LABELS[t.status as TaskState] || t.status}`, {
              icon: '🔄',
              duration: 3000,
              style: { fontSize: '12px', fontWeight: 'bold' },
            });
          }
        });
      }
      prevTasksRef.current = newHash;
      
      setTasks(newTasks);
      setLastRefresh(Date.now());
    } catch (err) {
      console.error('Failed to fetch tasks:', err);
    } finally {
      setIsLoading(false);
    }
  }, [tasks]);

  useEffect(() => {
    fetchTasks();
    // Poll every 5 seconds for real-time kanban updates
    const interval = setInterval(fetchTasks, 5000);
    return () => clearInterval(interval);
  }, []);

  const completedCount = tasks.filter(t => ['completed', 'closed'].includes(t.status)).length;
  const totalCount = tasks.length;
  const resolutionRate = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0;

  const timeAgo = (dateStr?: string) => {
    if (!dateStr) return '';
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  };

  const secondsSinceRefresh = Math.floor((Date.now() - lastRefresh) / 1000);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 text-brand-600 animate-spin" />
        <span className="ml-3 text-gray-500">Loading tasks...</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="mb-6 flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-headline font-semibold text-brand-900">Task Board</h2>
          <p className="text-sm text-gray-500">Real-time kanban — auto-refreshes every 5s.</p>
        </div>
        <div className="flex gap-2 items-center">
          <div className="flex items-center gap-2 bg-white border border-warm-border rounded-2xl px-4 py-2 shadow-sm">
            <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
            <span className="text-xs font-bold text-slate-700">Live</span>
          </div>
          <div className="bg-white border border-warm-border rounded-2xl px-4 py-2 flex items-center gap-2 shadow-sm">
            <TrendingUp className="w-4 h-4 text-emerald-500" />
            <span className="text-xs font-bold text-slate-700">Resolution: {resolutionRate}%</span>
          </div>
          <button
            onClick={() => { setIsLoading(true); fetchTasks(); }}
            className="p-2 bg-white border border-warm-border rounded-xl hover:bg-gray-50 transition-colors shadow-sm"
          >
            <RefreshCw className="w-4 h-4 text-gray-500" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-x-auto pb-4 custom-scrollbar">
        <div className="flex gap-4 min-w-max h-full">
          {STAGES.map((stage) => {
            const stageTasks = tasks.filter(t => t.status === stage.id);
            return (
              <div key={stage.id} className="w-72 flex flex-col bg-slate-50/50 rounded-[28px] border border-warm-border p-3">
                <div className="flex items-center justify-between mb-3 px-2">
                  <div className="flex items-center gap-2">
                    <div className={cn("w-2.5 h-2.5 rounded-full", stage.dotColor)} />
                    <h3 className="font-bold text-sm text-slate-900">{stage.label}</h3>
                    <span className="bg-slate-200 text-slate-600 text-[10px] font-bold px-2 py-0.5 rounded-full">
                      {stageTasks.length}
                    </span>
                  </div>
                </div>

                <div className="flex-1 overflow-y-auto space-y-2 pr-1">
                  {stageTasks.map(task => (
                    <div
                      key={task.task_id}
                      className={cn(
                        "bg-white p-3.5 rounded-2xl border shadow-sm hover:shadow-md transition-all cursor-pointer group",
                        stage.id === 'completed' && "border-emerald-200 bg-emerald-50/30",
                        stage.id === 'closed' && "border-slate-200 bg-slate-50/50 opacity-70",
                        stage.id !== 'completed' && stage.id !== 'closed' && "border-warm-border"
                      )}
                    >
                      <div className="flex justify-between items-start mb-2">
                        <span className="text-[10px] font-mono font-bold text-brand-600 px-1.5 py-0.5 bg-brand-50 rounded border border-brand-100">
                          {task.task_id.slice(-8)}
                        </span>
                        <div className={cn(
                          "w-2 h-2 rounded-full",
                          (task.match_score || 0) > 0.8 ? 'bg-red-500' : (task.match_score || 0) > 0.5 ? 'bg-amber-500' : 'bg-slate-300'
                        )} />
                      </div>
                      
                      <h4 className="text-xs font-bold text-slate-900 mb-1 group-hover:text-brand-600 transition-colors truncate">
                        Need: {task.need_id.slice(-8)}
                      </h4>
                      
                      {task.outcome_status && (
                        <span className={cn(
                          "text-[9px] font-black uppercase px-2 py-0.5 rounded-full inline-block mb-1",
                          task.outcome_status === 'need_fully_met' ? 'bg-emerald-100 text-emerald-700' :
                          task.outcome_status === 'partially_met' ? 'bg-amber-100 text-amber-700' :
                          'bg-red-100 text-red-700'
                        )}>
                          {task.outcome_status.replace(/_/g, ' ')}
                        </span>
                      )}

                      <div className="flex items-center justify-between mt-3 pt-2 border-t border-slate-50">
                        <div className="flex items-center gap-1.5">
                          <div className="w-5 h-5 rounded-full bg-slate-100 flex items-center justify-center border border-slate-200">
                            <User className="w-2.5 h-2.5 text-slate-500" />
                          </div>
                          <span className="text-[9px] font-medium text-slate-500 truncate max-w-[80px]">
                            {task.assigned_volunteer_id ? task.assigned_volunteer_id.slice(-6) : 'Pending'}
                          </span>
                        </div>
                        <div className="flex items-center gap-1 text-[9px] text-slate-400">
                          <Clock className="w-3 h-3" />
                          <span>{timeAgo(task.completed_at || task.started_at || task.dispatched_at || task.created_at)}</span>
                        </div>
                      </div>
                    </div>
                  ))}

                  {stageTasks.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-8 opacity-30">
                      {stage.id === 'closed' ? (
                        <Lock className="w-6 h-6 text-slate-300 mb-1" />
                      ) : (
                        <CheckCircle2 className="w-6 h-6 text-slate-300 mb-1" />
                      )}
                      <p className="text-[10px] font-medium">Empty</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Play, CheckCircle2, Clock, ChevronRight, User, AlertTriangle,
  Zap, MapPin, ArrowRight, Loader2, RefreshCw, ClipboardCheck,
  MessageSquare, Star, FileText
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { TaskAPI } from '../../api/endpoints';
import { useAuthStore } from '../../stores/auth.store';
import { TASK_STATE_LABELS, TASK_STATE_COLORS } from '../../constants/taskStates';
import type { TaskState, OutcomeStatus } from '../../constants/taskStates';
import { cn } from '../../lib/utils';
import { toast } from 'react-hot-toast';

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
  briefing_text?: string;
}

export const VolunteerHomePage: React.FC = () => {
  const navigate = useNavigate();
  const { user_id, display_name } = useAuthStore();
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [completionModal, setCompletionModal] = useState<TaskRow | null>(null);
  const [outcomeStatus, setOutcomeStatus] = useState<OutcomeStatus>('need_fully_met');
  const [outcomeNotes, setOutcomeNotes] = useState('');
  const [followUp, setFollowUp] = useState(false);

  const fetchTasks = useCallback(async () => {
    try {
      const res = await TaskAPI.list({ limit: 50 });
      const allTasks = Array.isArray(res.data) ? res.data : res.data?.items || [];
      // Show tasks assigned to current user in actionable states
      const myTasks = allTasks.filter((t: TaskRow) =>
        t.assigned_volunteer_id === user_id &&
        ['dispatched', 'accepted', 'in_progress', 'completed'].includes(t.status)
      );
      setTasks(myTasks);
    } catch (err) {
      console.error('Failed to fetch tasks:', err);
    } finally {
      setLoading(false);
    }
  }, [user_id]);

  useEffect(() => {
    fetchTasks();
    // Poll every 10s for real-time feel
    const interval = setInterval(fetchTasks, 10000);
    return () => clearInterval(interval);
  }, [fetchTasks]);

  const handleAccept = async (task: TaskRow) => {
    setActionLoading(task.task_id);
    try {
      await TaskAPI.accept(task.task_id, user_id!);
      toast.success('Task accepted');
      fetchTasks();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Accept failed');
    } finally {
      setActionLoading(null);
    }
  };

  const handleStart = async (task: TaskRow) => {
    setActionLoading(task.task_id);
    try {
      await TaskAPI.start(task.task_id, user_id!);
      toast.success('Task started');
      fetchTasks();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Start failed');
    } finally {
      setActionLoading(null);
    }
  };

  const handleComplete = async () => {
    if (!completionModal) return;
    setActionLoading(completionModal.task_id);
    try {
      await TaskAPI.complete(completionModal.task_id, user_id!, {
        outcome_status: outcomeStatus,
        outcome_notes: outcomeNotes,
        follow_up_required: followUp,
      });
      toast.success('Task completed! Great work.');
      setCompletionModal(null);
      setOutcomeNotes('');
      setFollowUp(false);
      fetchTasks();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Completion failed');
    } finally {
      setActionLoading(null);
    }
  };

  const statusConfig: Record<string, { color: string; icon: React.ReactNode; action: string }> = {
    dispatched: {
      color: 'bg-blue-500',
      icon: <Zap className="w-5 h-5 text-white" />,
      action: 'Accept Task',
    },
    accepted: {
      color: 'bg-indigo-500',
      icon: <ArrowRight className="w-5 h-5 text-white" />,
      action: 'Start Work',
    },
    in_progress: {
      color: 'bg-amber-500',
      icon: <Play className="w-5 h-5 text-white fill-current" />,
      action: 'Mark Complete',
    },
    completed: {
      color: 'bg-emerald-500',
      icon: <CheckCircle2 className="w-5 h-5 text-white" />,
      action: 'Awaiting Close',
    },
  };

  const timeAgo = (dateStr?: string) => {
    if (!dateStr) return '';
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  };

  const activeTasks = tasks.filter(t => ['dispatched', 'accepted', 'in_progress'].includes(t.status));
  const completedTasks = tasks.filter(t => t.status === 'completed');

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-black p-4 pb-24">
      {/* Header */}
      <header className="flex justify-between items-center pt-6 mb-8">
        <div className="space-y-1">
          <h1 className="text-3xl font-black text-slate-900 dark:text-white tracking-tight">My Tasks</h1>
          <div className="flex items-center gap-2 px-3 py-1 bg-white dark:bg-slate-900 rounded-full shadow-sm border border-slate-100 dark:border-slate-800">
            <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
            <span className="text-[10px] font-black uppercase text-slate-500 tracking-widest">
              Volunteer Active
            </span>
          </div>
        </div>
        <button
          onClick={() => { setLoading(true); fetchTasks(); }}
          className="w-12 h-12 bg-slate-900 dark:bg-white rounded-2xl flex items-center justify-center shadow-lg shadow-slate-900/20 active:scale-90 transition-transform"
        >
          <RefreshCw className={cn("w-5 h-5 text-white dark:text-slate-900", loading && "animate-spin")} />
        </button>
      </header>

      {loading ? (
        <div className="flex flex-col items-center justify-center py-20 space-y-4">
          <Loader2 className="w-10 h-10 text-blue-500 animate-spin" />
          <p className="text-slate-500 font-bold">Loading assignments...</p>
        </div>
      ) : (
        <div className="space-y-8">
          {/* Active Tasks */}
          {activeTasks.length > 0 && (
            <div className="space-y-4">
              <h3 className="text-sm font-black uppercase tracking-widest text-slate-400 px-2">
                Active ({activeTasks.length})
              </h3>
              {activeTasks.map((task) => {
                const config = statusConfig[task.status] || statusConfig.dispatched;
                const isActioning = actionLoading === task.task_id;
                return (
                  <motion.div
                    key={task.task_id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="bg-white dark:bg-slate-900 rounded-3xl shadow-xl border border-slate-100 dark:border-slate-800 overflow-hidden"
                  >
                    {/* Status Bar */}
                    <div className={cn("h-1.5", config.color)} />

                    <div className="p-5 space-y-4">
                      <div className="flex justify-between items-start">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className={cn(
                              "text-[10px] font-black uppercase px-2 py-0.5 rounded-full",
                              TASK_STATE_COLORS[task.status as TaskState]
                            )}>
                              {TASK_STATE_LABELS[task.status as TaskState]}
                            </span>
                          </div>
                          <p className="text-xs font-mono text-slate-400">
                            Task #{task.task_id.slice(-8)}
                          </p>
                        </div>
                        <div className="flex items-center gap-1 text-[10px] text-slate-400">
                          <Clock className="w-3 h-3" />
                          {timeAgo(task.dispatched_at || task.created_at)}
                        </div>
                      </div>

                      {/* Need + Household Info */}
                      <div className="bg-slate-50 dark:bg-slate-800 rounded-2xl p-4 space-y-2">
                        <div className="flex justify-between text-xs">
                          <span className="font-black text-slate-400 uppercase tracking-widest">Need</span>
                          <span className="font-mono font-bold text-slate-700 dark:text-slate-300">
                            {task.need_id.slice(0, 12)}...
                          </span>
                        </div>
                        {task.household_id && (
                          <div className="flex justify-between text-xs">
                            <span className="font-black text-slate-400 uppercase tracking-widest">Household</span>
                            <span className="font-mono font-bold text-slate-700 dark:text-slate-300">
                              {task.household_id.slice(0, 12)}...
                            </span>
                          </div>
                        )}
                        {task.match_score && (
                          <div className="flex justify-between text-xs">
                            <span className="font-black text-slate-400 uppercase tracking-widest">Match</span>
                            <span className="font-mono font-bold text-emerald-600">
                              {(task.match_score * 100).toFixed(0)}%
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Action Button */}
                      {task.status !== 'completed' && (
                        <button
                          disabled={isActioning}
                          onClick={() => {
                            if (task.status === 'dispatched') handleAccept(task);
                            else if (task.status === 'accepted') handleStart(task);
                            else if (task.status === 'in_progress') setCompletionModal(task);
                          }}
                          className={cn(
                            "w-full font-black py-4 rounded-2xl flex items-center justify-center gap-3 active:scale-[0.98] transition-all shadow-lg text-white",
                            task.status === 'dispatched' && "bg-blue-600 shadow-blue-500/30",
                            task.status === 'accepted' && "bg-indigo-600 shadow-indigo-500/30",
                            task.status === 'in_progress' && "bg-amber-500 shadow-amber-500/30",
                            isActioning && "opacity-60"
                          )}
                        >
                          {isActioning ? (
                            <Loader2 className="w-5 h-5 animate-spin" />
                          ) : (
                            <>
                              {config.icon}
                              {config.action}
                            </>
                          )}
                        </button>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}

          {/* Completed awaiting close */}
          {completedTasks.length > 0 && (
            <div className="space-y-4">
              <h3 className="text-sm font-black uppercase tracking-widest text-emerald-500 px-2">
                Completed ({completedTasks.length})
              </h3>
              {completedTasks.map((task) => (
                <div
                  key={task.task_id}
                  className="bg-emerald-50 dark:bg-emerald-900/20 rounded-3xl p-5 border-2 border-emerald-100 dark:border-emerald-900/30"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-emerald-500 rounded-2xl flex items-center justify-center shadow-lg shadow-emerald-500/20">
                      <CheckCircle2 className="w-5 h-5 text-white" />
                    </div>
                    <div className="flex-1">
                      <p className="text-xs font-black text-emerald-700 dark:text-emerald-400">COMPLETED</p>
                      <p className="text-[10px] font-mono text-emerald-600/60">
                        Task #{task.task_id.slice(-8)} · Awaiting coordinator review
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Empty State */}
          {tasks.length === 0 && (
            <div className="text-center py-20 space-y-4">
              <div className="w-20 h-20 bg-slate-100 dark:bg-slate-800 rounded-full flex items-center justify-center mx-auto">
                <ClipboardCheck className="w-10 h-10 text-slate-300" />
              </div>
              <div className="space-y-1">
                <p className="text-slate-900 dark:text-white font-bold text-xl">No active tasks</p>
                <p className="text-slate-400 text-sm">You'll be notified when new tasks are dispatched.</p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Completion Modal */}
      <AnimatePresence>
        {completionModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-end justify-center p-4"
            onClick={() => setCompletionModal(null)}
          >
            <motion.div
              initial={{ y: 200 }}
              animate={{ y: 0 }}
              exit={{ y: 200 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-white dark:bg-slate-900 rounded-t-[32px] rounded-b-3xl w-full max-w-md p-8 space-y-6 shadow-2xl"
            >
              <div className="text-center space-y-2">
                <div className="w-16 h-16 bg-emerald-100 dark:bg-emerald-900/30 rounded-full flex items-center justify-center mx-auto">
                  <CheckCircle2 className="w-8 h-8 text-emerald-600" />
                </div>
                <h3 className="text-xl font-black text-slate-900 dark:text-white">Complete Task</h3>
                <p className="text-slate-500 text-xs">Task #{completionModal.task_id.slice(-8)}</p>
              </div>

              {/* Outcome Status */}
              <div className="space-y-3">
                <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">Outcome</label>
                <div className="grid grid-cols-2 gap-2">
                  {([
                    { id: 'need_fully_met', label: 'Fully Met', color: 'emerald' },
                    { id: 'partially_met', label: 'Partial', color: 'amber' },
                    { id: 'unresolved', label: 'Unresolved', color: 'red' },
                    { id: 'follow_up_required', label: 'Follow-up', color: 'blue' },
                  ] as { id: OutcomeStatus; label: string; color: string }[]).map((o) => (
                    <button
                      key={o.id}
                      type="button"
                      onClick={() => setOutcomeStatus(o.id)}
                      className={cn(
                        "py-3 rounded-xl text-xs font-black transition-all border-2",
                        outcomeStatus === o.id
                          ? `bg-${o.color}-500 border-${o.color}-500 text-white shadow-lg`
                          : "bg-white dark:bg-slate-800 border-slate-100 dark:border-slate-700 text-slate-500"
                      )}
                    >
                      {o.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Notes */}
              <div className="space-y-2">
                <label className="text-[10px] font-black uppercase tracking-widest text-slate-400">Notes</label>
                <textarea
                  value={outcomeNotes}
                  onChange={(e) => setOutcomeNotes(e.target.value)}
                  placeholder="What did you observe?"
                  className="w-full bg-slate-50 dark:bg-slate-800 border-2 border-slate-100 dark:border-slate-700 rounded-2xl p-4 text-sm min-h-[80px] focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Follow-up */}
              <label className="flex items-center gap-3 p-3 bg-slate-50 dark:bg-slate-800 rounded-xl cursor-pointer">
                <input
                  type="checkbox"
                  checked={followUp}
                  onChange={(e) => setFollowUp(e.target.checked)}
                  className="w-5 h-5 rounded border-2 border-slate-300"
                />
                <span className="text-xs font-bold text-slate-600">Follow-up required</span>
              </label>

              {/* Submit */}
              <button
                onClick={handleComplete}
                disabled={actionLoading === completionModal.task_id}
                className="w-full bg-emerald-500 text-white font-black py-5 rounded-2xl shadow-xl shadow-emerald-500/30 flex items-center justify-center gap-2 active:scale-95 transition-transform disabled:opacity-50"
              >
                {actionLoading === completionModal.task_id ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <>
                    <CheckCircle2 className="w-5 h-5" />
                    Submit Completion
                  </>
                )}
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Bottom Nav */}
      <div className="fixed bottom-0 left-0 right-0 p-4 bg-transparent pointer-events-none">
        <div className="bg-white/80 dark:bg-slate-900/80 backdrop-blur-2xl px-8 py-4 rounded-[32px] border border-white/20 shadow-2xl flex justify-between items-center pointer-events-auto max-w-sm mx-auto">
          <button className="text-blue-600"><ClipboardCheck className="w-6 h-6" /></button>
          <button onClick={() => navigate('/field')} className="text-slate-400"><MapPin className="w-6 h-6" /></button>
          <button className="text-slate-400"><User className="w-6 h-6" /></button>
        </div>
      </div>
    </div>
  );
};

export default VolunteerHomePage;

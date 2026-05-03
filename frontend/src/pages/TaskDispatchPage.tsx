import React, { useState, useEffect } from 'react';
import { Loader2, Play, CheckCircle, XCircle, Users, Zap, Star, ArrowRight, RefreshCw, BarChart3 } from 'lucide-react';
import { TaskAPI, VolunteerAPI, AnalyticsAPI } from '../api/endpoints';
import { VALID_TRANSITIONS, TASK_STATE_LABELS, TASK_STATE_COLORS, canTransition } from '../constants/taskStates';
import type { TaskState, OutcomeStatus } from '../constants/taskStates';
import { toast } from 'react-hot-toast';

export function TaskDispatchPage() {
  const [tasks, setTasks] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('');
  const [selectedTask, setSelectedTask] = useState<any>(null);
  const [matches, setMatches] = useState<any[]>([]);
  const [isLoadingMatches, setIsLoadingMatches] = useState(false);

  const fetchTasks = async () => {
    setIsLoading(true);
    try {
      const res = await TaskAPI.list({ status: statusFilter || undefined, limit: 50 }) as any;
      const newTasks = Array.isArray(res.data) ? res.data : res.data?.items || [];
      setTasks(newTasks);
      // Auto-update selectedTask if it changed
      if (selectedTask) {
        const updated = newTasks.find((t: any) => t.task_id === selectedTask.task_id);
        if (updated && updated.status !== selectedTask.status) {
          setSelectedTask(updated);
          toast(`Task status → ${updated.status}`, { icon: '🔄' });
        }
      }
    } catch { toast.error('Failed to load tasks'); }
    finally { setIsLoading(false); }
  };

  useEffect(() => { fetchTasks(); }, [statusFilter]);

  // Auto-refresh every 8 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      TaskAPI.list({ status: statusFilter || undefined, limit: 50 }).then((res: any) => {
        const newTasks = Array.isArray(res.data) ? res.data : res.data?.items || [];
        setTasks(newTasks);
        if (selectedTask) {
          const updated = newTasks.find((t: any) => t.task_id === selectedTask.task_id);
          if (updated && updated.status !== selectedTask.status) {
            setSelectedTask(updated);
          }
        }
      }).catch(() => {});
    }, 8000);
    return () => clearInterval(interval);
  }, [statusFilter, selectedTask]);


  const fetchMatches = async (taskId: string) => {
    setIsLoadingMatches(true);
    try {
      const res = await TaskAPI.getMatches(taskId);
      setMatches(res.data.candidates || []);
    } catch { toast.error('Failed to load matches'); setMatches([]); }
    finally { setIsLoadingMatches(false); }
  };

  const handleSelectTask = (task: any) => {
    setSelectedTask(task);
    setMatches([]);
    if (task.status === 'unassigned') {
      fetchMatches(task.task_id);
    }
  };

  // ── State machine transitions ─────────────────────────────
  const handleDispatch = async (taskId: string, volunteerId: string) => {
    try {
      await TaskAPI.dispatch(taskId, { volunteer_id: volunteerId });
      toast.success('Task dispatched');
      fetchTasks();
      setSelectedTask(null);
    } catch (e: any) { toast.error(e?.response?.data?.detail || 'Dispatch failed'); }
  };

  const handleAccept = async (taskId: string, volunteerId: string) => {
    try {
      await TaskAPI.accept(taskId, volunteerId);
      toast.success('Task accepted');
      fetchTasks();
    } catch (e: any) { toast.error(e?.response?.data?.detail || 'Accept failed'); }
  };

  const handleStart = async (taskId: string, volunteerId: string) => {
    try {
      await TaskAPI.start(taskId, volunteerId);
      toast.success('Task started');
      fetchTasks();
    } catch (e: any) { toast.error(e?.response?.data?.detail || 'Start failed'); }
  };

  const handleComplete = async (taskId: string, volunteerId: string) => {
    try {
      await TaskAPI.complete(taskId, volunteerId, {
        outcome_status: 'need_fully_met',
        outcome_notes: 'Completed via coordinator UI',
        follow_up_required: false,
      });
      toast.success('Task completed');
      fetchTasks();
    } catch (e: any) { toast.error(e?.response?.data?.detail || 'Complete failed'); }
  };

  const handleClose = async (taskId: string) => {
    try {
      await TaskAPI.close(taskId, { volunteer_rating: 5 });
      toast.success('Task closed');
      // Trigger feedback loop: writes to household_history + updates analytics
      try {
        await AnalyticsAPI.processFeedback(taskId);
        toast.success('Analytics & history updated', { icon: '📊', duration: 3000 });
      } catch (fbErr: any) {
        // Non-blocking — close succeeded, feedback processing can retry
        console.warn('Feedback loop error (non-critical):', fbErr?.response?.data?.detail || fbErr);
      }
      fetchTasks();
    } catch (e: any) { toast.error(e?.response?.data?.detail || 'Close failed'); }
  };

  // ── Complete with rating modal ──────────────────────────────
  const handleCompleteWithOutcome = async (
    taskId: string, volunteerId: string,
    outcome_status: string = 'need_fully_met',
    outcome_notes: string = 'Completed via coordinator UI',
    follow_up_required: boolean = false,
  ) => {
    try {
      await TaskAPI.complete(taskId, volunteerId, { outcome_status, outcome_notes, follow_up_required });
      toast.success('Task completed');
      fetchTasks();
    } catch (e: any) { toast.error(e?.response?.data?.detail || 'Complete failed'); }
  };

  return (
    <div className="flex h-full gap-6">
      {/* Left: Task list */}
      <div className="w-1/2 flex flex-col">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-2xl font-headline font-semibold text-brand-900">Task Dispatch</h2>
          <button onClick={fetchTasks} className="p-2 hover:bg-gray-100 rounded-xl"><RefreshCw className="w-4 h-4" /></button>
        </div>

        <div className="flex gap-1 bg-gray-100 p-1 rounded-xl mb-4 flex-wrap">
          {['', 'unassigned', 'dispatched', 'accepted', 'in_progress', 'completed', 'closed'].map(s => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold ${statusFilter === s ? 'bg-white text-brand-600 shadow-sm' : 'text-gray-500'}`}>
              {s || 'All'}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="flex items-center gap-2 py-10 justify-center"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : (
          <div className="space-y-2 overflow-auto flex-1">
            {tasks.map((t: any) => (
              <div key={t.task_id} onClick={() => handleSelectTask(t)}
                className={`p-3 rounded-xl border cursor-pointer transition-all ${
                  selectedTask?.task_id === t.task_id ? 'border-brand-400 bg-brand-50' : 'border-gray-100 bg-white hover:border-gray-300'
                }`}>
                <div className="flex justify-between items-center">
                  <span className="font-mono text-xs text-brand-900">{t.task_id?.slice(0, 12)}</span>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${TASK_STATE_COLORS[t.status as TaskState] || 'bg-gray-100'}`}>
                    {TASK_STATE_LABELS[t.status as TaskState] || t.status}
                  </span>
                </div>
                <p className="text-xs text-gray-500 mt-1">Need: {t.need_id?.slice(0, 12)}</p>
              </div>
            ))}
            {tasks.length === 0 && <p className="text-center text-gray-400 py-8">No tasks found</p>}
          </div>
        )}
      </div>

      {/* Right: Detail + Matches */}
      <div className="w-1/2 flex flex-col">
        {selectedTask ? (
          <div className="space-y-4">
            <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">
              <h3 className="font-bold text-brand-900 mb-3">Task Detail</h3>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div><span className="text-gray-500">ID:</span> <span className="font-mono">{selectedTask.task_id?.slice(0, 16)}</span></div>
                <div><span className="text-gray-500">Status:</span> <span className="font-bold">{selectedTask.status}</span></div>
                <div><span className="text-gray-500">Need:</span> <span className="font-mono">{selectedTask.need_id?.slice(0, 16)}</span></div>
                <div><span className="text-gray-500">Volunteer:</span> <span className="font-mono">{selectedTask.assigned_volunteer_id?.slice(0, 12) || 'None'}</span></div>
                <div><span className="text-gray-500">Match Score:</span> <span className="font-mono">{selectedTask.match_score?.toFixed(3) || 'N/A'}</span></div>
              </div>

              {/* Valid transitions */}
              <div className="mt-4 pt-3 border-t border-gray-100">
                <p className="text-xs font-bold text-gray-400 mb-2">ACTIONS (valid transitions)</p>
                <div className="flex flex-wrap gap-2">
                  {VALID_TRANSITIONS[selectedTask.status as TaskState]?.map((next: TaskState) => (
                    <button key={next} onClick={() => {
                      if (next === 'dispatched' && selectedTask.assigned_volunteer_id) handleDispatch(selectedTask.task_id, selectedTask.assigned_volunteer_id);
                      else if (next === 'accepted') handleAccept(selectedTask.task_id, selectedTask.assigned_volunteer_id);
                      else if (next === 'in_progress') handleStart(selectedTask.task_id, selectedTask.assigned_volunteer_id);
                      else if (next === 'completed') handleComplete(selectedTask.task_id, selectedTask.assigned_volunteer_id);
                      else if (next === 'closed') handleClose(selectedTask.task_id);
                    }}
                      className="flex items-center gap-1 px-3 py-1.5 bg-brand-600 text-white text-xs font-bold rounded-lg hover:bg-brand-800">
                      <ArrowRight className="w-3 h-3" /> {TASK_STATE_LABELS[next]}
                    </button>
                  ))}
                  {(VALID_TRANSITIONS[selectedTask.status as TaskState]?.length || 0) === 0 && (
                    <span className="text-xs text-gray-400">Terminal state — no transitions</span>
                  )}
                </div>
              </div>
            </div>

            {/* Match candidates (top 3) */}
            {selectedTask.status === 'unassigned' && (
              <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">
                <h3 className="font-bold text-brand-900 mb-3 flex items-center gap-2">
                  <Users className="w-4 h-4" /> Match Candidates
                </h3>
                {isLoadingMatches ? (
                  <Loader2 className="w-5 h-5 animate-spin mx-auto" />
                ) : matches.length === 0 ? (
                  <p className="text-xs text-gray-400">No candidates found</p>
                ) : (
                  <div className="space-y-2">
                    {matches.slice(0, 3).map((m: any, i: number) => (
                      <div key={m.volunteer_id} className="flex items-center justify-between p-3 bg-gray-50 rounded-xl">
                        <div>
                          <p className="font-mono text-xs">{m.volunteer_id?.slice(0, 12)}</p>
                          <p className="text-[10px] text-gray-500">
                            Score: {m.match_score?.toFixed(3)} · Cosine: {m.cosine_score?.toFixed(3)} · Dist: {m.distance_km?.toFixed(1)}km
                          </p>
                          <p className="text-[10px] text-gray-400">
                            Boosts: {JSON.stringify(m.boosts_applied || {})} · Fatigue: {m.fatigue_penalty?.toFixed(2)}
                          </p>
                        </div>
                        <button onClick={() => handleDispatch(selectedTask.task_id, m.volunteer_id)}
                          className="px-3 py-1.5 bg-brand-600 text-white text-xs font-bold rounded-lg hover:bg-brand-800 flex items-center gap-1">
                          <Zap className="w-3 h-3" /> Dispatch
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {/* GAP-01: Override record — graceful */}
                <div className="mt-3 p-2 bg-yellow-50 rounded-lg text-xs text-yellow-700">
                  Override recording (GAP-01): Feature coming soon
                </div>

                {/* GAP-07: Briefing preview — graceful */}
                <div className="mt-2 p-2 bg-yellow-50 rounded-lg text-xs text-yellow-700">
                  Briefing preview (GAP-07): Feature coming soon
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400">
            <p>Select a task to view details</p>
          </div>
        )}
      </div>
    </div>
  );
}

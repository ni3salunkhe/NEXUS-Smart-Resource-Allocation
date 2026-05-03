import React, { useState, useEffect } from 'react';
import { useUiStore } from '../../stores/ui.store';
import { X, Bot, ShieldCheck, Check, Loader2, AlertCircle } from 'lucide-react';
import { cn } from '../../lib/utils';
import { TaskAPI } from '../../api/endpoints';
import { toast } from 'react-hot-toast';

interface TaskDispatchModalProps {
  taskId: string;
}

interface MatchCandidate {
  volunteer_id: string;
  display_name?: string;
  match_score: number;
  distance_km?: number;
  skills?: string[];
  total_deployments?: number;
}

export function TaskDispatchModal({ taskId }: TaskDispatchModalProps) {
  const { closePanel } = useUiStore();
  const [candidates, setCandidates] = useState<MatchCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [dispatching, setDispatching] = useState<string | null>(null);
  const [manualVolId, setManualVolId] = useState('');

  useEffect(() => {
    const fetchMatches = async () => {
      setLoading(true);
      try {
        const res = await TaskAPI.getMatches(taskId, 15);
        setCandidates(res.data.candidates || res.data || []);
      } catch (err) {
        console.error('Failed to fetch matches:', err);
        toast.error('Failed to load volunteer matches');
      } finally {
        setLoading(false);
      }
    };
    fetchMatches();
  }, [taskId]);

  const handleDispatch = async (volunteerId: string, isOverride: boolean = false) => {
    setDispatching(volunteerId);
    try {
      await TaskAPI.dispatch(taskId, { volunteer_id: volunteerId, auto_dispatch: !isOverride });
      if (isOverride) {
        try {
          await TaskAPI.recordOverride({
            task_id: taskId,
            selected_volunteer_id: volunteerId,
            reason: 'Coordinator manual override',
          });
        } catch (e) {
          // Override recording is non-blocking
          console.warn('Override recording failed:', e);
        }
      }
      toast.success(`Task dispatched to ${volunteerId.slice(0, 8)}!`);
      closePanel();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Dispatch failed');
    } finally {
      setDispatching(null);
    }
  };

  const handleManualDispatch = () => {
    if (!manualVolId.trim()) {
      toast.error('Enter a volunteer ID');
      return;
    }
    handleDispatch(manualVolId.trim(), true);
  };

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-white rounded-3xl shadow-2xl max-w-3xl w-full flex flex-col max-h-[90vh] overflow-hidden">
        
        <div className="flex items-center justify-between p-4 border-b border-warm-border bg-slate-50">
          <div>
            <h3 className="font-bold text-lg text-brand-900 tracking-tight flex items-center gap-2">
              Dispatch Task
              <span className="bg-brand-100 text-brand-700 text-xs font-mono px-2 py-0.5 rounded border border-brand-200">
                {taskId.slice(0, 12)}
              </span>
            </h3>
            <p className="text-xs text-gray-500 mt-1">Algorithm matches ranked by proximity, skills, and success rate</p>
          </div>
          <button 
            onClick={closePanel}
            className="p-1.5 text-gray-500 hover:text-brand-600 hover:bg-brand-50 rounded-md transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 bg-white">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-8 h-8 text-brand-600 animate-spin" />
              <span className="ml-3 text-gray-500">Finding best matches...</span>
            </div>
          ) : candidates.length === 0 ? (
            <div className="text-center py-16">
              <AlertCircle className="w-12 h-12 text-gray-300 mx-auto mb-3" />
              <p className="text-gray-500 font-medium">No volunteer matches found</p>
              <p className="text-xs text-gray-400 mt-1">Try expanding search radius or use manual dispatch below</p>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 mb-4 text-sm font-semibold text-brand-600 bg-brand-50 p-3 rounded-lg border border-brand-100">
                <Bot className="w-5 h-5" />
                Algorithm found {candidates.length} candidates ranked by match score.
              </div>

              <div className="space-y-4 cursor-default">
                {candidates.map((candidate, idx) => {
                  const isBest = idx === 0;
                  const scorePercent = Math.round((candidate.match_score || 0) * 100);
                  const isDispatching = dispatching === candidate.volunteer_id;

                  return (
                    <div 
                      key={candidate.volunteer_id}
                      className={cn(
                        "rounded-lg p-4 relative transition-colors",
                        isBest ? "border-2 border-green-500 bg-green-50/30" : "border border-warm-border bg-white hover:border-brand-200"
                      )}
                    >
                      {isBest && (
                        <div className="absolute top-0 right-0 bg-green-500 text-white text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-bl-lg rounded-tr-md flex items-center gap-1">
                          <Check className="w-3 h-3" /> Best Match
                        </div>
                      )}
                      <div className="flex justify-between items-start">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-full bg-brand-100 flex items-center justify-center text-brand-600 font-bold border border-brand-200">
                            {(candidate.display_name || candidate.volunteer_id).charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <h4 className="font-bold text-brand-900">
                              {candidate.display_name || `Vol-${candidate.volunteer_id.slice(0, 8)}`}
                            </h4>
                            <span className="text-xs text-gray-500">
                              {candidate.distance_km ? `${candidate.distance_km.toFixed(1)}km away` : 'Distance N/A'}
                              {candidate.skills?.length ? ` • ${candidate.skills[0]}` : ''}
                            </span>
                          </div>
                        </div>
                        <div className="text-right">
                          <div className={cn(
                            "text-2xl font-mono font-bold",
                            scorePercent >= 80 ? "text-green-600" : scorePercent >= 60 ? "text-amber-600" : "text-gray-600"
                          )}>
                            {scorePercent}%
                          </div>
                          <div className="text-[10px] uppercase tracking-widest text-gray-400 font-semibold">Match Score</div>
                        </div>
                      </div>
                      <div className="mt-3 flex justify-end gap-2">
                        {isBest ? (
                          <button 
                            onClick={() => handleDispatch(candidate.volunteer_id)}
                            disabled={!!dispatching}
                            className="flex-1 bg-brand-600 text-white font-medium py-2 rounded shadow-sm hover:bg-brand-800 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                          >
                            {isDispatching ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                            {isDispatching ? 'Dispatching...' : 'Dispatch'}
                          </button>
                        ) : (
                          <button 
                            onClick={() => handleDispatch(candidate.volunteer_id, true)}
                            disabled={!!dispatching}
                            className="text-sm text-brand-600 font-medium px-4 py-1.5 border border-brand-200 bg-brand-50 hover:bg-brand-100 rounded transition-colors disabled:opacity-50"
                          >
                            {isDispatching ? 'Dispatching...' : 'Override & Dispatch'}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
          
          {/* Coordinator Override — always shown */}
          <div className="mt-6 pt-6 border-t border-warm-border">
            <h4 className="text-sm font-bold text-gray-700 mb-3 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4" /> Coordinator Override
            </h4>
            <div className="flex gap-2">
              <input 
                type="text" 
                value={manualVolId}
                onChange={(e) => setManualVolId(e.target.value)}
                placeholder="Enter specific Volunteer ID..." 
                className="flex-1 border border-warm-border rounded p-2 text-sm focus:outline-none focus:border-brand-400 focus:ring-1 focus:ring-brand-400"
              />
              <button 
                onClick={handleManualDispatch}
                disabled={!!dispatching}
                className="bg-slate-50 border border-warm-border text-brand-900 font-medium px-4 py-2 rounded text-sm hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                Manual Dispatch
              </button>
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}

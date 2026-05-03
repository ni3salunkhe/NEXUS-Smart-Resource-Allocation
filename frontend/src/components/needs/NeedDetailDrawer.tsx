import { X, ExternalLink, MapPin, ShieldAlert, FileText, Send, Loader2 } from 'lucide-react';
import { useUiStore } from '../../stores/ui.store';
import { UrgencyBadge } from '../ui/UrgencyBadge';
import { cn } from '../../lib/utils';
import { useState, useEffect } from 'react';
import { NeedAPI, TaskAPI } from '../../api/endpoints';
import { toast } from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';

interface NeedDetailDrawerProps {
  needId: string;
}

interface NeedDetail {
  need_id: string;
  category: string;
  subcategory?: string;
  description: string;
  urgency_score: number;
  severity_score?: number;
  status: string;
  ward_id?: string;
  household_id?: string;
  vulnerability_flags?: Record<string, boolean>;
  source?: string;
  language_detected?: string;
  created_at?: string;
  ingested_at?: string;
}

export function NeedDetailDrawer({ needId }: NeedDetailDrawerProps) {
  const { closePanel } = useUiStore();
  const navigate = useNavigate();
  const [isClosing, setIsClosing] = useState(false);
  const [need, setNeed] = useState<NeedDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [dispatching, setDispatching] = useState(false);

  useEffect(() => {
    const fetchNeed = async () => {
      setLoading(true);
      try {
        const res = await NeedAPI.get(needId);
        setNeed(res.data);
      } catch (err) {
        console.error('Failed to fetch need:', err);
        toast.error('Failed to load need details');
      } finally {
        setLoading(false);
      }
    };
    fetchNeed();
  }, [needId]);

  const handleClose = () => {
    setIsClosing(true);
    setTimeout(() => { closePanel(); }, 300);
  };

  const handleDispatch = async () => {
    if (!need) return;
    setDispatching(true);
    try {
      const res = await TaskAPI.create({ need_id: need.need_id, household_id: need.household_id });
      toast.success(`Task ${res.data.task_id} created. Redirecting to dispatch...`);
      closePanel();
      navigate('/tasks');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to create task');
    } finally {
      setDispatching(false);
    }
  };

  const vulnFlags = need?.vulnerability_flags || {};
  const activeFlags = Object.keys(vulnFlags).filter(k => vulnFlags[k]);

  return (
    <>
      <div 
        className={cn(
          "fixed inset-0 bg-black/20 z-40 backdrop-blur-sm transition-opacity duration-300",
          isClosing ? "opacity-0" : "opacity-100"
        )}
        onClick={handleClose} 
      />
      <div 
        className={cn(
          "fixed right-0 top-0 bottom-0 w-[450px] bg-white z-50 shadow-2xl border-l border-warm-border transform transition-transform duration-300 ease-in-out flex flex-col",
          isClosing ? "translate-x-full" : "translate-x-0"
        )}
      >
        <div className="flex items-center justify-between p-4 border-b border-warm-border bg-slate-50">
          <div className="flex items-center gap-3">
            <h3 className="font-bold text-lg text-brand-900 tracking-tight">
              {typeof needId === 'string' ? needId.slice(0, 12) : needId}
            </h3>
            {need && (
              <span className={cn(
                "text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded",
                need.status === 'unverified' ? "bg-amber-100 text-amber-700" :
                need.status === 'verified' ? "bg-blue-100 text-blue-700" :
                need.status === 'assigned' ? "bg-indigo-100 text-indigo-700" :
                "bg-gray-100 text-gray-600"
              )}>
                {need.status}
              </span>
            )}
          </div>
          <button 
            onClick={handleClose}
            className="p-1.5 text-gray-500 hover:text-brand-600 hover:bg-brand-50 rounded-md transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-8">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <Loader2 className="w-8 h-8 text-brand-600 animate-spin" />
              <span className="ml-3 text-gray-500">Loading need...</span>
            </div>
          ) : need ? (
            <>
              <section>
                <div className="flex justify-between items-start mb-2">
                  <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-2">Urgency Evaluation</h4>
                  <UrgencyBadge score={need.urgency_score || 0} />
                </div>
                
                <div className="bg-slate-50 p-4 rounded-3xl border border-warm-border space-y-3 mt-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">Urgency Score</span>
                    <span className="font-mono font-medium">{(need.urgency_score || 0).toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">Severity Score</span>
                    <span className="font-mono font-medium">{(need.severity_score || 0).toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">Category</span>
                    <span className="font-mono font-medium capitalize">{need.category}</span>
                  </div>
                  {need.subcategory && (
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Subcategory</span>
                      <span className="font-mono font-medium capitalize">{need.subcategory.replace(/_/g, ' ')}</span>
                    </div>
                  )}
                  <div className="h-px bg-warm-border w-full my-2"></div>
                  <div className="flex justify-between font-bold text-brand-900">
                    <span>Final Score</span>
                    <span className="font-mono">{(need.urgency_score || 0).toFixed(2)}</span>
                  </div>
                </div>
              </section>

              <section>
                <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">Report Details</h4>
                <div className="space-y-4">
                  <div className="bg-gray-50 p-4 rounded-lg border-l-4 border-category-health text-sm text-gray-700 leading-relaxed">
                    "{need.description || 'No description provided'}"
                  </div>
                  
                  <div className="flex items-start gap-3">
                    <MapPin className="w-5 h-5 text-gray-400 mt-0.5" />
                    <div>
                      <div className="text-sm font-semibold text-brand-900">Ward: {need.ward_id || 'Unknown'}</div>
                      {need.household_id && (
                        <div className="text-xs text-gray-500 flex items-center gap-1 mt-1">
                          Matched Household: <span className="font-mono text-brand-600 hover:underline cursor-pointer">{need.household_id.slice(0, 12)}</span>
                          <ExternalLink className="w-3 h-3 text-brand-400" />
                        </div>
                      )}
                    </div>
                  </div>
                  
                  <div className="flex items-start gap-3">
                    <FileText className="w-5 h-5 text-gray-400 mt-0.5" />
                    <div>
                      <div className="text-sm font-semibold text-brand-900">Source: {need.source || 'Direct'}</div>
                      {need.language_detected && (
                        <div className="text-xs text-gray-500 mt-1">Language: {need.language_detected}</div>
                      )}
                    </div>
                  </div>
                </div>
              </section>

              <section>
                <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3">Vulnerability Context</h4>
                <div className="flex flex-wrap gap-2">
                  {activeFlags.length > 0 ? activeFlags.map(flag => (
                    <span key={flag} className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-red-50 text-red-700 border border-red-200 rounded-md text-xs font-semibold uppercase tracking-tight">
                      <ShieldAlert className="w-4 h-4" /> {flag.replace(/_/g, ' ')}
                    </span>
                  )) : (
                    <span className="text-gray-400 text-xs font-medium">No vulnerability flags</span>
                  )}
                </div>
              </section>
            </>
          ) : (
            <div className="text-center py-20 text-gray-400">
              <p>Failed to load need details</p>
            </div>
          )}
        </div>

        <div className="p-4 border-t border-warm-border bg-slate-50 flex gap-3">
          <button 
            onClick={handleClose}
            className="flex-1 bg-white border border-warm-border text-brand-900 font-semibold py-2.5 rounded-lg shadow-sm hover:bg-gray-50 transition-colors flex justify-center items-center gap-2"
          >
            Close
          </button>
          <button 
            onClick={handleDispatch}
            disabled={dispatching || !need}
            className="flex-1 bg-brand-600 text-white font-semibold py-2.5 rounded-lg shadow-sm hover:bg-brand-800 transition-colors flex justify-center items-center gap-2 disabled:opacity-50"
          >
            {dispatching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            {dispatching ? 'Creating...' : 'Dispatch Task'}
          </button>
        </div>
      </div>
    </>
  );
}

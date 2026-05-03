import { X, Lock, Users, AlertCircle, Phone, HeartPulse } from 'lucide-react';
import { useUiStore } from '../../stores/ui.store';
import { useHouseholdStore } from '../../stores/household.store';
import { UrgencyBadge } from '../ui/UrgencyBadge';
import { cn } from '../../lib/utils';
import { useState, useEffect } from 'react';
import { HouseholdAPI } from '../../api/endpoints';
import { toast } from 'react-hot-toast';

interface HouseholdDetailDrawerProps {
  householdId: string;
}

export function HouseholdDetailDrawer({ householdId }: HouseholdDetailDrawerProps) {
  const { closePanel } = useUiStore();
  const { getHousehold } = useHouseholdStore();
  const [isClosing, setIsClosing] = useState(false);
  const [activeTab, setActiveTab] = useState<'details' | 'history' | 'consent'>('details');
  const [history, setHistory] = useState<any[]>([]);
  const [consents, setConsents] = useState<any[]>([]);
  const [isLoadingExtra, setIsLoadingExtra] = useState(false);

  const household = getHousehold(householdId);

  useEffect(() => {
    if (!householdId) return;
    const fetchExtra = async () => {
      setIsLoadingExtra(true);
      try {
        const [histRes, consRes] = await Promise.allSettled([
          HouseholdAPI.getHistory(householdId),
          HouseholdAPI.getConsent(householdId) // GAP-06
        ]);
        if (histRes.status === 'fulfilled') setHistory(histRes.value.data);
        if (consRes.status === 'fulfilled') setConsents(consRes.value.data);
      } catch (err) {
        console.error(err);
      } finally {
        setIsLoadingExtra(false);
      }
    };
    fetchExtra();
  }, [householdId]);

  const handleOptOut = async () => {
    if (confirm('DPDP Act 2023 Warning: This action will permanently mark this household as opted-out from data processing. Proceed?')) {
      try {
        await HouseholdAPI.optOut(householdId);
        toast.success('Household opted out');
        closePanel();
      } catch (err) {
        toast.error('Failed to opt out');
      }
    }
  };

  if (!household) return null;

  const handleClose = () => {
    setIsClosing(true);
    setTimeout(() => {
      closePanel();
    }, 300);
  };

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
          "fixed right-0 top-0 bottom-0 w-[500px] bg-white z-50 shadow-2xl border-l border-warm-border transform transition-transform duration-300 ease-in-out flex flex-col",
          isClosing ? "translate-x-full" : "translate-x-0"
        )}
      >
        <div className="flex items-center justify-between p-4 border-b border-warm-border bg-slate-50">
          <div>
            <h3 className="font-bold text-lg text-brand-900 tracking-tight">{householdId.slice(0, 12)}</h3>
            <span className="text-xs text-gray-500">Status: {household.status}</span>
          </div>
          <div className="flex gap-2">
            <button 
              onClick={handleOptOut}
              className="text-xs bg-red-100 text-red-600 px-2 py-1 rounded hover:bg-red-200 font-bold"
            >
              Opt-Out
            </button>
            <button 
              onClick={handleClose}
              className="p-1.5 text-gray-500 hover:text-brand-600 hover:bg-brand-50 rounded-md transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="flex border-b border-warm-border px-4">
          <button onClick={() => setActiveTab('details')} className={`py-2 px-4 text-sm font-bold ${activeTab === 'details' ? 'border-b-2 border-brand-600 text-brand-600' : 'text-gray-500'}`}>Details</button>
          <button onClick={() => setActiveTab('history')} className={`py-2 px-4 text-sm font-bold ${activeTab === 'history' ? 'border-b-2 border-brand-600 text-brand-600' : 'text-gray-500'}`}>History</button>
          <button onClick={() => setActiveTab('consent')} className={`py-2 px-4 text-sm font-bold ${activeTab === 'consent' ? 'border-b-2 border-brand-600 text-brand-600' : 'text-gray-500'}`}>Consent</button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-8 text-left">
          {activeTab === 'details' && (
            <>
              <section>
            <div className="bg-white p-4 rounded-lg border border-warm-border shadow-sm">
              <div className="flex justify-between items-start mb-4">
                <div className="flex items-center gap-2">
                  <Users className="w-5 h-5 text-brand-600" />
                  <h4 className="font-bold text-brand-900 text-sm uppercase tracking-widest">Demographics</h4>
                </div>
                <div className="bg-brand-50 text-brand-700 px-2 py-1 rounded text-xs font-bold font-mono">
                  {household.total_members} Members
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm text-left">
                <div>
                  <span className="block text-gray-400 text-xs uppercase tracking-widest font-semibold mb-1">Dwelling</span>
                  <span className="text-gray-900 font-medium capitalize prose-sm">{household.dwelling_type || 'Unknown'}</span>
                </div>
                <div>
                  <span className="block text-gray-400 text-xs uppercase tracking-widest font-semibold mb-1">Economic</span>
                  <span className="text-gray-900 font-medium prose-sm">{household.economic_tier || 'Not Set'}</span>
                </div>
              </div>
              <div className="mt-4 pt-4 border-t border-gray-50">
                   <span className="block text-gray-400 text-xs uppercase tracking-widest font-semibold mb-2">Location Context</span>
                   <p className="text-sm text-gray-700 italic font-headline">{household.location_description || 'No description'}</p>
              </div>
            </div>
          </section>

          <section>
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest flex items-center gap-2">
                <Lock className="w-4 h-4" /> Vulnerability & Score
              </h4>
            </div>
            
            <div className="bg-slate-50 p-4 rounded-3xl border border-warm-border">
              <div className="flex justify-between text-sm mb-2">
                <span className="text-gray-600">Vulnerability Score</span>
                <span className="font-mono font-bold">{(household.vulnerability_score || 0).toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-gray-600">Data Quality</span>
                <span className="font-mono font-medium">{(household.data_quality_score || 0).toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-gray-600">Crisis Frequency</span>
                <span className="font-mono font-medium">{(household.crisis_frequency || 0).toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Needs Reported</span>
                <span className="font-mono font-medium">{household.total_needs_reported || 0}</span>
              </div>
            </div>
          </section>

          <section>
            <h4 className="text-xs font-bold text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-2">
              <AlertCircle className="w-4 h-4" /> Ward & Assistance
            </h4>
            <div className="bg-white p-4 rounded-lg border border-warm-border shadow-sm space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600">Ward ID</span>
                <span className="font-mono font-medium">{household.ward_id || 'N/A'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Tasks Completed</span>
                <span className="font-mono font-medium">{household.total_tasks_completed || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Total Assistance</span>
                <span className="font-mono font-medium">₹{household.total_assistance_value || 0}</span>
              </div>
            </div>
          </section>
          </>
          )}

          {activeTab === 'history' && (
            <section>
              <h4 className="text-sm font-bold text-gray-900 mb-4">Event History</h4>
              {isLoadingExtra ? <p className="text-xs text-gray-500">Loading...</p> : history.length === 0 ? <p className="text-xs text-gray-500">No history found.</p> : (
                <div className="space-y-3">
                  {history.map((h, i) => (
                    <div key={i} className="text-sm p-3 border rounded bg-slate-50">
                      <div className="font-bold">{h.event_type}</div>
                      <div className="text-xs text-gray-500">{new Date(h.event_timestamp).toLocaleString()}</div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {activeTab === 'consent' && (
            <section>
              <h4 className="text-sm font-bold text-gray-900 mb-4">Consents (GAP-06)</h4>
              {isLoadingExtra ? <p className="text-xs text-gray-500">Loading...</p> : consents.length === 0 ? (
                <div className="bg-yellow-50 text-yellow-800 p-4 rounded text-sm">
                  Feature coming soon. No consent records fetched.
                </div>
              ) : (
                <div className="space-y-3">
                  {consents.map((c, i) => (
                    <div key={i} className="text-sm p-3 border rounded bg-slate-50">
                      <div className="font-bold">{c.consent_type}</div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}
        </div>
      </div>
    </>
  );
}

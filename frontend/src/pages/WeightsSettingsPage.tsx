import React, { useState, useEffect } from 'react';
import { Loader2, Save, SlidersHorizontal } from 'lucide-react';
import { IntelligenceAPI } from '../api/endpoints';
import { toast } from 'react-hot-toast';

const WEIGHT_LABELS: Record<string, string> = {
  w1_severity: 'W1 — Severity',
  w2_recency: 'W2 — Recency (log decay)',
  w3_vulnerability: 'W3 — Vulnerability',
  w4_unmet_duration: 'W4 — Unmet Duration (sigmoid)',
  w5_source_reliability: 'W5 — Source Reliability',
  w6_crisis_frequency: 'W6 — Crisis Frequency',
  w7_coverage_penalty: 'W7 — Coverage Penalty',
};

export function WeightsSettingsPage() {
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [extras, setExtras] = useState<Record<string, any>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const res = await IntelligenceAPI.getWeights();
        const data = res.data;
        const w: Record<string, number> = {};
        const e: Record<string, any> = {};
        Object.entries(data).forEach(([k, v]) => {
          if (k.startsWith('w') && k.includes('_')) w[k] = v as number;
          else e[k] = v;
        });
        setWeights(w);
        setExtras(e);
      } catch { toast.error('Failed to load weights'); }
      finally { setIsLoading(false); }
    })();
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await IntelligenceAPI.updateWeights({ ...weights, ...extras });
      toast.success('Weights updated');
    } catch { toast.error('Failed to save weights'); }
    finally { setIsSaving(false); }
  };

  if (isLoading) return <div className="flex items-center gap-2 py-10 justify-center"><Loader2 className="w-5 h-5 animate-spin" /></div>;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-3 mb-6">
        <SlidersHorizontal className="w-6 h-6 text-brand-600" />
        <h2 className="text-2xl font-headline font-semibold text-brand-900">Urgency Weight Configuration</h2>
      </div>

      <section className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm space-y-6">
        {Object.entries(WEIGHT_LABELS).map(([key, label]) => (
          <div key={key}>
            <div className="flex justify-between mb-1">
              <label className="text-sm font-bold text-gray-700">{label}</label>
              <span className="font-mono text-sm text-brand-600">{(weights[key] ?? 0).toFixed(2)}</span>
            </div>
            <input type="range" min="0" max="1" step="0.01"
              value={weights[key] ?? 0}
              onChange={e => setWeights(w => ({ ...w, [key]: parseFloat(e.target.value) }))}
              className="w-full accent-brand-600" />
          </div>
        ))}
      </section>

      <section className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm space-y-4">
        <h3 className="font-bold text-brand-900">Thresholds</h3>
        <div className="grid grid-cols-2 gap-4">
          {['chronic_threshold', 'chronic_floor', 'escalation_threshold', 'escalation_minutes'].map(k => (
            <div key={k}>
              <label className="text-xs font-bold text-gray-500 uppercase">{k.replace(/_/g, ' ')}</label>
              <input type="number" step="0.01"
                value={extras[k] ?? ''}
                onChange={e => setExtras(x => ({ ...x, [k]: parseFloat(e.target.value) }))}
                className="w-full bg-gray-50 rounded-xl p-2 text-sm border-none mt-1" />
            </div>
          ))}
        </div>
      </section>

      <button onClick={handleSave} disabled={isSaving}
        className="w-full bg-brand-600 text-white py-3 rounded-xl font-bold hover:bg-brand-800 disabled:opacity-50 flex items-center justify-center gap-2">
        {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
        Save Weights
      </button>
    </div>
  );
}

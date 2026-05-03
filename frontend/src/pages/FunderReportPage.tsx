import React, { useState, useEffect } from 'react';
import { Loader2, Shield, Download } from 'lucide-react';
import { AnalyticsAPI } from '../api/endpoints';
import { toast } from 'react-hot-toast';

export function FunderReportPage() {
  const [report, setReport] = useState<any>(null);
  const [months, setMonths] = useState(3);
  const [isLoading, setIsLoading] = useState(true);

  const fetchReport = async () => {
    setIsLoading(true);
    try {
      const res = await AnalyticsAPI.getFunderReport(months);
      setReport(res.data);
    } catch { toast.error('Failed to load funder report'); }
    finally { setIsLoading(false); }
  };

  useEffect(() => { fetchReport(); }, [months]);

  if (isLoading) return <div className="flex items-center gap-2 py-10 justify-center"><Loader2 className="w-5 h-5 animate-spin" /></div>;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-headline font-semibold text-brand-900 flex items-center gap-2">
            <Shield className="w-6 h-6 text-green-600" /> Funder Report
          </h2>
          <p className="text-xs text-gray-500 mt-1">Anonymized data only — no PII, no individual records.</p>
        </div>
        <select value={months} onChange={e => setMonths(+e.target.value)}
          className="bg-white border border-gray-200 rounded-xl px-3 py-2 text-sm">
          {[1, 3, 6, 12].map(m => <option key={m} value={m}>{m} month{m > 1 ? 's' : ''}</option>)}
        </select>
      </div>

      {report ? (
        <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">
          <pre className="text-xs font-mono whitespace-pre-wrap text-gray-700 max-h-[60vh] overflow-auto">
            {JSON.stringify(report, null, 2)}
          </pre>
        </div>
      ) : (
        <p className="text-gray-400 text-center py-10">No report data</p>
      )}
    </div>
  );
}

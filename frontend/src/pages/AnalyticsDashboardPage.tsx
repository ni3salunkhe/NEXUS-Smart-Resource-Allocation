import React, { useState, useEffect, useCallback } from 'react';
import { BarChart3, TrendingUp, TrendingDown, Minus, Loader2, Users, Home, Activity, AlertTriangle, RefreshCw } from 'lucide-react';
import { AnalyticsAPI, IntelligenceAPI } from '../api/endpoints';
import { toast } from 'react-hot-toast';

export function AnalyticsDashboardPage() {
  const [metrics, setMetrics] = useState<any>(null);
  const [hii, setHii] = useState<any[]>([]);
  const [volPerf, setVolPerf] = useState<any[]>([]);
  const [dupRate, setDupRate] = useState<any>(null);
  const [gapReport, setGapReport] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const loadAll = useCallback(async () => {
    try {
      const [metricsRes, hiiRes, volRes, dupRes, gapRes] = await Promise.allSettled([
        AnalyticsAPI.getImpactMetrics({ period_type: 'monthly', limit: 1 }),
        AnalyticsAPI.getHouseholdImprovement({ window_days: 30, limit: 10 }),
        AnalyticsAPI.getVolunteerPerformance({ limit: 10 }),
        AnalyticsAPI.getDuplicationRate(30),
        IntelligenceAPI.getGapReport(),
      ]);
      if (metricsRes.status === 'fulfilled') {
        const data = metricsRes.value.data;
        setMetrics(Array.isArray(data) ? data[0] : data);
      }
      if (hiiRes.status === 'fulfilled') setHii(Array.isArray(hiiRes.value.data) ? hiiRes.value.data : hiiRes.value.data.items || []);
      if (volRes.status === 'fulfilled') setVolPerf(Array.isArray(volRes.value.data) ? volRes.value.data : volRes.value.data.items || []);
      if (dupRes.status === 'fulfilled') setDupRate(dupRes.value.data);
      if (gapRes.status === 'fulfilled') setGapReport(gapRes.value.data);
    } catch { toast.error('Failed to load analytics'); }
    finally { setIsLoading(false); setIsRefreshing(false); }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleRecompute = async () => {
    setIsRefreshing(true);
    try {
      await AnalyticsAPI.computeMetrics({ period_type: 'monthly' });
      toast.success('Metrics recomputed');
      await loadAll();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Recompute failed');
      setIsRefreshing(false);
    }
  };

  if (isLoading) return <div className="flex items-center gap-2 py-10 justify-center"><Loader2 className="w-5 h-5 animate-spin" /> Loading analytics...</div>;

  const resolutionRate = metrics ? ((metrics.needs_resolution_rate || 0) * 100).toFixed(1) : null;

  const trendIcon = (trend: string) => {
    if (trend === 'improving') return <TrendingUp className="w-4 h-4 text-green-500" />;
    if (trend === 'worsening') return <TrendingDown className="w-4 h-4 text-red-500" />;
    return <Minus className="w-4 h-4 text-gray-400" />;
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-start">
        <h2 className="text-2xl font-headline font-semibold text-brand-900">Analytics Dashboard</h2>
        <button
          onClick={handleRecompute}
          disabled={isRefreshing}
          className="flex items-center gap-2 bg-brand-900 text-white px-4 py-2 rounded-xl text-sm font-bold hover:bg-brand-700 disabled:opacity-50"
        >
          {isRefreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          Recompute Metrics
        </button>
      </div>

      {/* Resolution Rate Hero */}
      {resolutionRate !== null && (
        <div className="bg-gradient-to-r from-brand-900 to-brand-700 rounded-3xl p-8 text-white flex items-center justify-between shadow-xl">
          <div>
            <p className="text-[10px] font-black text-brand-200 uppercase tracking-widest mb-1">Overall Resolution Rate</p>
            <p className="text-6xl font-black">{resolutionRate}%</p>
            <p className="text-brand-300 text-sm mt-1">{metrics?.needs_resolved ?? 0} of {metrics?.needs_reported ?? 0} needs resolved this month</p>
          </div>
          <TrendingUp className="w-20 h-20 text-white/20" />
        </div>
      )}

      {/* Impact Metric Cards */}
      {metrics && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MetricCard label="Households Served" value={metrics.households_served} icon={<Home className="w-5 h-5" />} />
          <MetricCard label="Needs Reported" value={metrics.needs_reported} icon={<Activity className="w-5 h-5" />} />
          <MetricCard label="Needs Resolved" value={metrics.needs_resolved} icon={<BarChart3 className="w-5 h-5" />} />
          <MetricCard label="Resolution Rate" value={`${((metrics.needs_resolution_rate || 0) * 100).toFixed(1)}%`} icon={<TrendingUp className="w-5 h-5" />} />
          <MetricCard label="Avg Assignment (min)" value={metrics.avg_time_to_assignment_min?.toFixed(1)} icon={<Activity className="w-5 h-5" />} />
          <MetricCard label="Active Volunteers" value={metrics.volunteers_active} icon={<Users className="w-5 h-5" />} />
          <MetricCard label="Volunteer Retention" value={`${((metrics.volunteer_retention_rate || 0) * 100).toFixed(1)}%`} icon={<Users className="w-5 h-5" />} />
          <MetricCard label="Resource Deserts" value={metrics.resource_desert_count} icon={<AlertTriangle className="w-5 h-5" />} />
        </div>
      )}

      {/* Duplication Rate */}
      {dupRate && (
        <div className="bg-white p-4 rounded-2xl border border-gray-100 shadow-sm">
          <h3 className="font-bold text-brand-900 mb-2">Duplication Rate (30d)</h3>
          <p className="text-2xl font-mono font-bold text-brand-600">{((dupRate.rate || dupRate.duplication_rate || 0) * 100).toFixed(1)}%</p>
        </div>
      )}

      {/* HII Table (worst-first) */}
      <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">
        <h3 className="font-bold text-brand-900 mb-4">Household Improvement Index (worst-first, 30d)</h3>
        {hii.length === 0 ? <p className="text-xs text-gray-400">No HII data</p> : (
          <table className="w-full text-sm">
            <thead><tr className="text-xs text-gray-400 uppercase">
              <th className="text-left py-2">Household</th>
              <th className="text-right">HII</th>
              <th className="text-right">Trend</th>
            </tr></thead>
            <tbody>
              {hii.map((h: any, i: number) => (
                <tr key={i} className="border-t border-gray-50">
                  <td className="py-2 font-mono text-xs">{(h.household_id || '').slice(0, 12)}</td>
                  <td className="text-right font-mono">{(h.improvement_index ?? h.hii_30d ?? 0).toFixed(2)}</td>
                  <td className="text-right flex justify-end items-center gap-1">{trendIcon(h.trend || h.trend_30d)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Volunteer Performance */}
      <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">
        <h3 className="font-bold text-brand-900 mb-4">Volunteer Performance</h3>
        {volPerf.length === 0 ? <p className="text-xs text-gray-400">No performance data</p> : (
          <table className="w-full text-sm">
            <thead><tr className="text-xs text-gray-400 uppercase">
              <th className="text-left py-2">Volunteer</th>
              <th className="text-right">Deployments</th>
              <th className="text-right">Rating</th>
            </tr></thead>
            <tbody>
              {volPerf.map((v: any, i: number) => (
                <tr key={i} className="border-t border-gray-50">
                  <td className="py-2 font-mono text-xs">{(v.volunteer_id || '').slice(0, 12)}</td>
                  <td className="text-right">{v.total_deployments ?? 0}</td>
                  <td className="text-right font-mono">{(v.outcome_rating ?? v.avg_rating ?? 0).toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Gap Report */}
      {gapReport && (
        <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm">
          <h3 className="font-bold text-brand-900 mb-3">Latest Gap Report</h3>
          <p className="text-sm text-gray-600">{gapReport.summary || JSON.stringify(gapReport).slice(0, 200)}</p>
          {gapReport.desert_wards && (
            <p className="text-xs text-red-600 mt-2">Desert wards: {gapReport.desert_wards.length}</p>
          )}
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value, icon }: { label: string; value: any; icon: React.ReactNode }) {
  return (
    <div className="bg-white p-4 rounded-2xl border border-gray-100 shadow-sm">
      <div className="flex items-center gap-2 text-brand-600 mb-2">{icon}<span className="text-xs font-bold text-gray-400 uppercase">{label}</span></div>
      <p className="text-2xl font-mono font-bold text-brand-900">{value ?? '—'}</p>
    </div>
  );
}

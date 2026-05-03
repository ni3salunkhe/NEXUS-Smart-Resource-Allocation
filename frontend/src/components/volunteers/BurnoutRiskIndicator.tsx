import React, { useState, useEffect } from 'react';
import { VolunteerAPI } from '../../api/endpoints';
import { AlertTriangle, Heart, Loader2 } from 'lucide-react';

interface BurnoutRiskIndicatorProps {
  volunteerId: string;
  compact?: boolean;
}

const LABEL_COLORS: Record<string, string> = {
  critical: 'bg-red-100 text-red-700 border-red-300',
  warning:  'bg-orange-100 text-orange-700 border-orange-300',
  moderate: 'bg-yellow-100 text-yellow-700 border-yellow-300',
  healthy:  'bg-green-100 text-green-700 border-green-300',
};

export function BurnoutRiskIndicator({ volunteerId, compact }: BurnoutRiskIndicatorProps) {
  const [data, setData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const res = await VolunteerAPI.getBurnout(volunteerId);
        setData(res.data);
      } catch {
        // graceful — endpoint may fail
      } finally {
        setIsLoading(false);
      }
    })();
  }, [volunteerId]);

  if (isLoading) return <Loader2 className="w-3 h-3 animate-spin text-gray-400" />;
  if (!data) return null;

  const label = data.label || 'healthy';
  const score = data.burnout_risk_score ?? 0;

  if (compact) {
    return (
      <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${LABEL_COLORS[label] || LABEL_COLORS.healthy}`}>
        {label.toUpperCase()} ({(score * 100).toFixed(0)}%)
      </span>
    );
  }

  return (
    <div className={`p-3 rounded-xl border ${LABEL_COLORS[label] || LABEL_COLORS.healthy}`}>
      <div className="flex items-center gap-2 mb-2">
        {label === 'critical' || label === 'warning'
          ? <AlertTriangle className="w-4 h-4" />
          : <Heart className="w-4 h-4" />}
        <span className="font-bold text-sm uppercase">{label}</span>
        <span className="ml-auto font-mono text-sm">{(score * 100).toFixed(0)}%</span>
      </div>
      <div className="grid grid-cols-2 gap-1 text-xs">
        <span>7d deploys: {data.deployments_7d}</span>
        <span>30d deploys: {data.deployments_30d}</span>
        <span>Consecutive: {data.consecutive_days}d</span>
        <span>Avg rating: {data.avg_outcome_rating?.toFixed(1)}</span>
      </div>
      {data.is_excluded && <p className="text-[10px] mt-1 font-bold">⛔ EXCLUDED from dispatch</p>}
      {data.is_warning && <p className="text-[10px] mt-1 font-bold">⚠️ Warning threshold reached</p>}
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { AlertTriangle, Filter, Loader2, RefreshCw, Search, Zap } from 'lucide-react';
import { IntelligenceAPI, TaskAPI } from '../api/endpoints';
import { toast } from 'react-hot-toast';

const CATEGORIES = ['', 'food', 'health', 'shelter', 'education', 'livelihood', 'water', 'mental_health', 'legal', 'hygiene', 'other'];

export function PriorityQueuePage() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [escalationCount, setEscalationCount] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [category, setCategory] = useState('');
  const [wardId, setWardId] = useState('');
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);

  const fetchQueue = async () => {
    setIsLoading(true);
    try {
      const res = await IntelligenceAPI.getPriorityQueue({
        limit, offset,
        category: category || undefined,
        ward_id: wardId || undefined,
      });
      setItems(res.data.items || []);
      setTotal(res.data.total || 0);
      setEscalationCount(res.data.escalations || 0);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load priority queue');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { fetchQueue(); }, [category, wardId, limit, offset]);

  const handleBatchRecompute = async () => {
    try {
      await IntelligenceAPI.batchRecompute();
      toast.success('Batch recompute triggered');
      fetchQueue();
    } catch { toast.error('Batch recompute failed'); }
  };

  const handleCreateTask = async (item: any) => {
    try {
      await TaskAPI.create({ need_id: item.need_id, household_id: item.household_id });
      toast.success('Task created successfully');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to create task');
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-headline font-semibold text-brand-900">Priority Queue</h2>
          <p className="text-sm text-gray-500 mt-1">
            {total} needs queued · <span className="text-red-600 font-bold">{escalationCount} escalations</span>
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleBatchRecompute}
            className="flex items-center gap-2 bg-gray-100 text-gray-700 px-4 py-2 rounded-xl text-sm font-bold hover:bg-gray-200">
            <RefreshCw className="w-4 h-4" /> Recompute All
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-4">
        <select value={category} onChange={e => { setCategory(e.target.value); setOffset(0); }}
          className="bg-white border border-gray-200 rounded-xl px-3 py-2 text-sm">
          <option value="">All Categories</option>
          {CATEGORIES.filter(Boolean).map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <input type="text" value={wardId} onChange={e => setWardId(e.target.value)}
          className="bg-white border border-gray-200 rounded-xl px-3 py-2 text-sm" placeholder="Ward ID filter" />
      </div>

      {isLoading ? (
        <div className="flex items-center gap-2 py-10 justify-center text-gray-500">
          <Loader2 className="w-5 h-5 animate-spin" /> Loading queue...
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <Zap className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="font-medium">Queue empty</p>
        </div>
      ) : (
        <div className="space-y-2 overflow-auto flex-1">
          {items.map((item: any, idx: number) => (
            <div key={item.need_id || idx}
              className={`bg-white p-4 rounded-2xl border shadow-sm flex items-center justify-between ${
                item.needs_escalation ? 'border-red-300 bg-red-50/30' : 'border-gray-100'
              }`}>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  {item.needs_escalation && <AlertTriangle className="w-4 h-4 text-red-500" />}
                  <span className="font-bold text-sm text-brand-900">{item.category}</span>
                  <span className="text-xs text-gray-400">· {item.ward_id || 'N/A'}</span>
                </div>
                <p className="text-xs text-gray-600 line-clamp-1">{item.description}</p>
              </div>
              <div className="flex items-center gap-4 ml-4">
                <UrgencyBadge score={item.urgency_score} needId={item.need_id} />
                <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded ${
                  item.status === 'unverified' ? 'bg-yellow-100 text-yellow-700' :
                  item.status === 'verified' ? 'bg-blue-100 text-blue-700' :
                  'bg-gray-100 text-gray-600'
                }`}>{item.status}</span>
                <button
                  onClick={() => handleCreateTask(item)}
                  className="bg-brand-600 text-white px-3 py-1.5 rounded-lg text-xs font-bold hover:bg-brand-700 transition-colors"
                >
                  Create Task
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {total > limit && (
        <div className="flex justify-center gap-2 mt-4 py-2">
          <button disabled={offset === 0} onClick={() => setOffset(o => Math.max(0, o - limit))}
            className="px-3 py-1 rounded bg-gray-100 text-sm disabled:opacity-40">Prev</button>
          <span className="text-sm text-gray-500 py-1">{offset + 1}–{Math.min(offset + limit, total)} of {total}</span>
          <button disabled={offset + limit >= total} onClick={() => setOffset(o => o + limit)}
            className="px-3 py-1 rounded bg-gray-100 text-sm disabled:opacity-40">Next</button>
        </div>
      )}
    </div>
  );
}

// ── URGENCY BADGE with score-history tooltip (T1-T7) ────────
function UrgencyBadge({ score, needId }: { score: number; needId: string }) {
  const [showTooltip, setShowTooltip] = useState(false);
  const [history, setHistory] = useState<any>(null);

  const handleMouseEnter = async () => {
    setShowTooltip(true);
    if (!history && needId) {
      try {
        const res = await IntelligenceAPI.getScoreHistory(needId, 1);
        const entries = res.data?.entries || res.data || [];
        if (entries.length > 0) setHistory(entries[0]);
      } catch { /* graceful */ }
    }
  };

  const color = score >= 0.9 ? 'bg-red-600' : score >= 0.7 ? 'bg-orange-500' : score >= 0.4 ? 'bg-yellow-500' : 'bg-green-500';

  return (
    <div className="relative" onMouseEnter={handleMouseEnter} onMouseLeave={() => setShowTooltip(false)}>
      <div className={`${color} text-white font-mono text-xs px-2 py-1 rounded-lg font-bold cursor-pointer`}>
        {score?.toFixed(2)}
      </div>
      {showTooltip && history && (
        <div className="absolute right-0 top-8 z-50 bg-white border border-gray-200 rounded-xl shadow-lg p-3 text-xs w-48">
          <p className="font-bold mb-2">Score Components</p>
          {['t1', 't2', 't3', 't4', 't5', 't6', 't7'].map(t => (
            <div key={t} className="flex justify-between">
              <span className="text-gray-500">{t}</span>
              <span className="font-mono">{(history[t] ?? 0).toFixed(3)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

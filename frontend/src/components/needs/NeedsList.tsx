import { useEffect, useState } from 'react';
import { useUiStore } from '../../stores/ui.store';
import { NeedCard } from './NeedCard';
import { NeedAPI } from '../../api/endpoints';
import { Loader2 } from 'lucide-react';

interface NeedRow {
  need_id: string;
  category: string;
  subcategory?: string;
  description: string;
  urgency_score: number;
  severity_score?: number;
  status: string;
  created_at?: string;
  ward_id?: string;
  vulnerability_flags?: Record<string, boolean>;
  household_id?: string;
}

export function NeedsList({ category, minUrgency }: { category: string, minUrgency: number }) {
  const [needs, setNeeds] = useState<NeedRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchNeeds = async () => {
      setIsLoading(true);
      try {
        const params: any = { limit: 50 };
        if (category !== 'all') params.category = category;
        const res = await NeedAPI.list(params);
        setNeeds(res.data);
      } catch (err) {
        console.error('Failed to fetch needs:', err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchNeeds();
  }, [category]);

  const filtered = needs.filter(n => n.urgency_score >= minUrgency);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 text-brand-600 animate-spin" />
        <span className="ml-3 text-gray-500">Loading needs...</span>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 pb-10">
      {filtered.map((need) => (
        <NeedCard key={need.need_id} need={need} />
      ))}
      {filtered.length === 0 && (
        <div className="col-span-full text-center py-16 text-gray-400">
          <p className="font-medium">No needs match current filters</p>
        </div>
      )}
    </div>
  );
}

import React from 'react';
import { useUiStore } from '../../stores/ui.store';
import { UrgencyBadge } from '../ui/UrgencyBadge';
import { Clock, MapPin, AlertCircle, HeartPulse, Droplets, Utensils, Home, FileText, Scale } from 'lucide-react';
import { cn } from '../../lib/utils';

export interface NeedCardProps {
  need: any;
  key?: React.Key;
}

const CategoryIcons: Record<string, any> = {
  health: HeartPulse,
  water: Droplets,
  food: Utensils,
  shelter: Home,
  documentation: FileText,
  legal: Scale,
};

const CategoryColors: Record<string, string> = {
  health: 'bg-category-health text-white',
  water: 'bg-category-water text-white',
  food: 'bg-category-food text-white',
  shelter: 'bg-category-shelter text-white',
  other: 'bg-category-other text-gray-800'
};

function timeAgo(dateStr?: string): string {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function NeedCard({ need }: NeedCardProps) {
  const { openPanel, activePanel, panelReferenceId } = useUiStore();
  const Icon = CategoryIcons[need.category] || AlertCircle;
  const colorClass = CategoryColors[need.category] || CategoryColors.other;

  const isSelected = activePanel === 'need_details' && panelReferenceId === need.need_id;
  const vulnFlags = need.vulnerability_flags || {};

  return (
    <div 
      onClick={() => openPanel('need_details', need.need_id)}
      className={cn(
        "bg-white border rounded-3xl overflow-hidden shadow-sm hover:shadow-md transition-all cursor-pointer flex flex-col group",
        isSelected ? "border-brand-400 ring-1 ring-brand-400" : "border-warm-border hover:border-brand-400"
      )}
    >
      <div className="flex px-5 py-4 border-b border-warm-border/60 bg-white justify-between items-start">
        <div className="flex gap-3">
          <div className={cn("p-2 rounded-lg flex-shrink-0 mt-0.5", colorClass)}>
            <Icon className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-brand-900 group-hover:text-brand-600 transition-colors uppercase tracking-tight text-sm">
                {typeof need.need_id === 'string' ? need.need_id.slice(0, 10) : need.need_id}
              </span>
              {need.subcategory && (
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider bg-gray-100 px-2 py-0.5 rounded-full">
                  {need.subcategory.replace(/_/g, ' ')}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 text-xs text-gray-500 mt-1">
              <span className="flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" /> {timeAgo(need.created_at || need.ingested_at)}
              </span>
              <span className="flex items-center gap-1 truncate max-w-[200px]">
                <MapPin className="w-3.5 h-3.5" /> {need.ward_id || 'Unknown area'}
              </span>
            </div>
          </div>
        </div>
        <UrgencyBadge score={need.urgency_score || 0} />
      </div>
      
      <div className="p-5 flex-1">
        <p className="text-sm text-gray-700 leading-relaxed line-clamp-2">
          {need.description || 'No description provided'}
        </p>
      </div>
      
      <div className="px-4 py-3 border-t border-warm-border bg-slate-50 flex items-center justify-between text-xs">
        <div className="flex gap-2">
          {Object.keys(vulnFlags).filter(k => vulnFlags[k]).map(flag => (
            <span key={flag} className="px-2 py-1 bg-red-50 text-red-700 font-medium rounded border border-red-100 uppercase tracking-tight text-[10px]">
              {flag.replace(/_/g, ' ')}
            </span>
          ))}
          {Object.keys(vulnFlags).filter(k => vulnFlags[k]).length === 0 && (
            <span className="text-gray-400 font-medium">Standard Priority</span>
          )}
        </div>
        <div>
          <span className={cn(
            "font-semibold uppercase tracking-wider px-2 py-1 rounded",
            need.status === 'unverified' ? "bg-amber-100 text-amber-700" :
            need.status === 'verified' ? "bg-blue-100 text-blue-700" :
            need.status === 'assigned' ? "bg-indigo-100 text-indigo-700" :
            need.status === 'in_progress' ? "bg-brand-100 text-brand-700" : "bg-gray-100 text-gray-600"
          )}>
            {need.status}
          </span>
        </div>
      </div>
    </div>
  );
}

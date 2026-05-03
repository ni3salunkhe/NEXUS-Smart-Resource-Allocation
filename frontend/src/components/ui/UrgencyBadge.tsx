import { cn } from '../../lib/utils';
import { AlertTriangle, AlertCircle, Info, Clock, CheckCircle } from 'lucide-react';

interface UrgencyBadgeProps {
  score: number; // 0.0 to 1.0
  className?: string;
}

export function getUrgencyConfig(score: number) {
  if (score >= 0.8) {
    return {
      label: 'Critical',
      colorClass: 'bg-urgency-critical text-warm-white',
      borderColor: 'border-urgency-critical',
      textColor: 'text-urgency-critical',
      icon: AlertTriangle,
    };
  }
  if (score >= 0.6) {
    return {
      label: 'High',
      colorClass: 'bg-urgency-high text-warm-white',
      borderColor: 'border-urgency-high',
      textColor: 'text-urgency-high',
      icon: AlertCircle,
    };
  }
  if (score >= 0.4) {
    return {
      label: 'Medium',
      colorClass: 'bg-urgency-medium text-warm-white',
      borderColor: 'border-urgency-medium',
      textColor: 'text-urgency-medium',
      icon: Clock,
    };
  }
  if (score >= 0.2) {
    return {
      label: 'Low',
      colorClass: 'bg-urgency-low text-warm-white',
      borderColor: 'border-urgency-low',
      textColor: 'text-urgency-low',
      icon: Info,
    };
  }
  return {
    label: 'Minimal',
    colorClass: 'bg-urgency-minimal text-warm-surface', // Minimal is #AEB6BF, might need dark text
    borderColor: 'border-urgency-minimal',
    textColor: 'text-urgency-minimal',
    icon: CheckCircle, // or something equivalent
  };
}

export function UrgencyBadge({ score, className }: UrgencyBadgeProps) {
  const config = getUrgencyConfig(score);
  const Icon = config.icon;
  
  return (
    <div className={cn("inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold shadow-sm border", config.colorClass, config.borderColor, className)}>
      <Icon className="w-3.5 h-3.5" />
      <span>{config.label}</span>
      <span className="opacity-90 font-mono ml-1">{score.toFixed(2)}</span>
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Utensils, HeartPulse, Home, GraduationCap, Briefcase, 
  Droplets, Brush, Brain, Scale, Plus, AlertTriangle,
  Users, Baby, Accessibility, Info, Languages, Send
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { NeedAPI, HouseholdAPI } from '../../api/endpoints';
import { Household } from '../../types/household.types';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const CATEGORIES = [
  { id: 'food', label: 'Food', icon: Utensils, color: 'text-orange-500', bg: 'bg-orange-50 dark:bg-orange-900/20' },
  { id: 'health', label: 'Health', icon: HeartPulse, color: 'text-red-500', bg: 'bg-red-50 dark:bg-red-900/20' },
  { id: 'shelter', label: 'Shelter', icon: Home, color: 'text-blue-500', bg: 'bg-blue-50 dark:bg-blue-900/20' },
  { id: 'education', label: 'Education', icon: GraduationCap, color: 'text-purple-500', bg: 'bg-purple-50 dark:bg-purple-900/20' },
  { id: 'livelihood', label: 'Livelihood', icon: Briefcase, color: 'text-emerald-500', bg: 'bg-emerald-50 dark:bg-emerald-900/20' },
  { id: 'water', label: 'Water', icon: Droplets, color: 'text-cyan-500', bg: 'bg-cyan-50 dark:bg-cyan-900/20' },
  { id: 'hygiene', label: 'Hygiene', icon: Brush, color: 'text-teal-500', bg: 'bg-teal-50 dark:bg-teal-900/20' },
  { id: 'mental_health', label: 'Mental Health', icon: Brain, color: 'text-indigo-500', bg: 'bg-indigo-50 dark:bg-indigo-900/20' },
  { id: 'legal', label: 'Legal', icon: Scale, color: 'text-amber-500', bg: 'bg-amber-50 dark:bg-amber-900/20' },
  { id: 'other', label: 'Other', icon: Plus, color: 'text-slate-500', bg: 'bg-slate-50 dark:bg-slate-900/20' },
];

interface NeedReportFormProps {
  household: Household;
  onSuccess: (data: any) => void;
}

export const NeedReportForm: React.FC<NeedReportFormProps> = ({ household, onSuccess }) => {
  const [category, setCategory] = useState<string>('');
  const [description, setDescription] = useState('');
  const [beneficiaries, setBeneficiaries] = useState(household.total_members || 1);
  const [isUrgent, setIsUrgent] = useState(false);
  const [flags, setFlags] = useState({ ...household.vulnerability_flags });
  const [language, setLanguage] = useState('en');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!category || description.length < 20) return;

    setLoading(true);
    try {
      const finalDescription = isUrgent ? `URGENT: ${description}` : description;
      const res = await NeedAPI.ingestMobile({
        category,
        description: finalDescription,
        latitude: household.location.lat,
        longitude: household.location.lng,
        beneficiary_count: beneficiaries,
        known_household_id: household.household_id,
        language,
        vulnerability_flags: flags as unknown as Record<string, boolean>
      });
      onSuccess(res.data);
    } catch (err) {
      console.error(err);
      alert('Submission failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-8 pb-24">
      {/* Household Summary Card */}
      <div className="bg-white dark:bg-slate-900 rounded-3xl p-6 shadow-xl border border-slate-100 dark:border-slate-800 relative overflow-hidden group">
        <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 blur-3xl -mr-16 -mt-16" />
        <div className="relative z-10 space-y-4">
           <div className="flex justify-between items-start">
             <div className="space-y-1">
               <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 leading-none">Selected Household</p>
               <p className="text-sm font-bold text-slate-900 dark:text-white">{household.location_description}</p>
             </div>
             <div className="flex -space-x-1">
                {household.vulnerability_flags.has_child && <div className="p-1.5 bg-amber-100 dark:bg-amber-900/30 rounded-full text-amber-600 outline outline-2 outline-white dark:outline-slate-900"><Baby className="w-3 h-3" /></div>}
                {household.vulnerability_flags.has_elderly && <div className="p-1.5 bg-purple-100 dark:bg-purple-900/30 rounded-full text-purple-600 outline outline-2 outline-white dark:outline-slate-900"><Users className="w-3 h-3" /></div>}
             </div>
           </div>
           
           {household.crisis_frequency > 0 && (
             <div className="bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-900/30 rounded-2xl p-3 flex items-center gap-3">
               <AlertTriangle className="w-5 h-5 text-red-500 shrink-0" />
               <p className="text-xs font-bold text-red-700 dark:text-red-400">
                 Household has needed help {household.crisis_frequency} times this month.
               </p>
             </div>
           )}
        </div>
      </div>

      {/* Category Grid */}
      <div className="space-y-4">
        <label className="text-sm font-black uppercase tracking-widest text-slate-400 pl-2">What is needed?</label>
        <div className="grid grid-cols-2 gap-3">
          {CATEGORIES.map((cat) => {
            const Icon = cat.icon;
            const isSelected = category === cat.id;
            return (
              <button
                key={cat.id}
                type="button"
                onClick={() => setCategory(cat.id)}
                className={cn(
                  "flex flex-col items-center justify-center gap-3 p-6 rounded-3xl transition-all border-2",
                  isSelected 
                    ? "bg-slate-900 dark:bg-white border-slate-900 dark:border-white shadow-xl shadow-slate-900/20 scale-[1.02]" 
                    : "bg-white dark:bg-slate-900 border-slate-100 dark:border-slate-800"
                )}
              >
                <div className={cn(
                  "p-3 rounded-2xl transition-colors",
                  isSelected ? "bg-white/10 dark:bg-slate-900/10 text-white dark:text-slate-900" : cn(cat.bg, cat.color)
                )}>
                  <Icon className="w-6 h-6" />
                </div>
                <span className={cn(
                  "text-[10px] font-black uppercase tracking-tighter",
                  isSelected ? "text-white dark:text-slate-900" : "text-slate-400"
                )}>
                  {cat.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Description */}
      <div className="space-y-4">
        <label className="text-sm font-black uppercase tracking-widest text-slate-400 pl-2">Description</label>
        <div className="relative">
          <textarea
            required
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder='Describe needs... (min 20 chars)'
            className="w-full bg-white dark:bg-slate-900 border-2 border-slate-100 dark:border-slate-800 rounded-3xl p-6 text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:border-blue-500 transition-all min-h-[160px] font-medium shadow-xl shadow-slate-900/5"
          />
          <div className="absolute bottom-6 right-6 text-[10px] font-black text-slate-300">
            {description.length}/500
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="grid grid-cols-2 gap-4">
         <div className="space-y-4">
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-400 pl-2">Total Beneficiaries</label>
            <div className="bg-white dark:bg-slate-900 rounded-2xl p-2 border-2 border-slate-100 dark:border-slate-800 flex items-center gap-2 shadow-lg shadow-slate-900/5">
               <button type="button" onClick={() => setBeneficiaries(Math.max(1, beneficiaries - 1))} className="p-3 bg-slate-50 dark:bg-slate-800 rounded-xl active:scale-90 transition-transform"><Plus className="w-4 h-4 rotate-45" /></button>
               <input 
                 type="number" 
                 value={beneficiaries} 
                 onChange={(e) => setBeneficiaries(parseInt(e.target.value))}
                 className="flex-1 bg-transparent text-center font-black text-slate-900 dark:text-white focus:outline-none"
               />
               <button type="button" onClick={() => setBeneficiaries(beneficiaries + 1)} className="p-3 bg-slate-50 dark:bg-slate-800 rounded-xl active:scale-90 transition-transform"><Plus className="w-4 h-4" /></button>
            </div>
         </div>

         <div className="space-y-4">
            <label className="text-[10px] font-black uppercase tracking-widest text-slate-400 pl-2">Priority</label>
            <button
              type="button"
              onClick={() => setIsUrgent(!isUrgent)}
              className={cn(
                "w-full h-[60px] rounded-2xl font-black text-xs transition-all flex items-center justify-center gap-2 border-2",
                isUrgent ? "bg-red-500 border-red-500 text-white shadow-lg shadow-red-500/30" : "bg-white dark:bg-slate-900 border-slate-100 dark:border-slate-800 text-slate-400"
              )}
            >
              <AlertTriangle className={cn("w-4 h-4", isUrgent ? "text-white" : "text-slate-300")} />
              {isUrgent ? 'URGENT' : 'NORMAL'}
            </button>
         </div>
      </div>

      {/* Language */}
      <div className="space-y-4">
        <label className="text-[10px] font-black uppercase tracking-widest text-slate-400 pl-2 flex items-center gap-2">
          <Languages className="w-3 h-3" />
          Submission Language
        </label>
        <div className="flex gap-2">
          {['en', 'hi', 'mr', 'ta'].map((lang) => (
            <button
              key={lang}
              type="button"
              onClick={() => setLanguage(lang)}
              className={cn(
                "flex-1 py-3 rounded-xl font-black text-xs transition-all",
                language === lang ? "bg-blue-600 text-white" : "bg-white dark:bg-slate-900 text-slate-400 border-2 border-slate-100 dark:border-slate-800"
              )}
            >
              {lang.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <button
        type="submit"
        disabled={loading || !category || description.length < 20}
        className="w-full bg-slate-900 dark:bg-white dark:text-slate-900 text-white font-black py-6 rounded-[32px] shadow-2xl flex items-center justify-center gap-3 active:scale-95 transition-transform disabled:opacity-50"
      >
        {loading ? (
          <div className="w-6 h-6 border-3 border-white/30 border-t-white rounded-full animate-spin" />
        ) : (
          <>
            <Send className="w-6 h-6" />
            Submit Need Report
          </>
        )}
      </button>
    </form>
  );
};

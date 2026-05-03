import React, { useState } from 'react';
import { Search, MapPin, Navigation, UserPlus, AlertCircle, Baby, Users, Accessibility, UserCheck } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { HouseholdAPI } from '../../api/endpoints';
import { Household } from '../../types/household.types';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface HouseholdLookupProps {
  onSelect: (household: Household) => void;
  onRegisterNew: () => void;
}

export const HouseholdLookup: React.FC<HouseholdLookupProps> = ({ onSelect, onRegisterNew }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Household[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const response = await HouseholdAPI.search({ query, limit: 10 });
      setResults(response.data || []);
    } catch (err) {
      setError('Search failed. Try again.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleGPS = () => {
    if (!navigator.geolocation) {
      setError('GPS not supported on this device.');
      return;
    }

    setLoading(true);
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const response = await HouseholdAPI.search({
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
            radius_m: 200,
            limit: 10
          });
          setResults(response.data || []);
        } catch (err) {
          setError('GPS search failed.');
        } finally {
          setLoading(false);
        }
      },
      (err) => {
        setError('Could not get your location.');
        setLoading(false);
      }
    );
  };

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-slate-900 rounded-3xl p-6 shadow-xl border border-slate-200 dark:border-slate-800">
        <h2 className="text-2xl font-bold text-slate-900 dark:text-white mb-2">Find Household</h2>
        <p className="text-slate-500 dark:text-slate-400 mb-6">Search by location description or use GPS to find households nearby.</p>
        
        <form onSubmit={handleSearch} className="space-y-4">
          <div className="relative group">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400 group-focus-within:text-blue-500 transition-colors" />
            <input
              type="text"
              placeholder='Try "near dargah" or "red door"...'
              className="w-full bg-slate-50 dark:bg-slate-800/50 border-2 border-slate-100 dark:border-slate-800 rounded-2xl py-4 pl-12 pr-4 text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:border-blue-500 transition-all font-medium"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-bold py-4 rounded-2xl transition-all shadow-lg shadow-blue-500/30 flex items-center justify-center gap-2"
            >
              Search
            </button>
            <button
              type="button"
              onClick={handleGPS}
              disabled={loading}
              className="bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 text-white font-bold p-4 rounded-2xl transition-all shadow-lg shadow-emerald-500/30 flex items-center justify-center"
              title="Use GPS"
            >
              <Navigation className="w-6 h-6" />
            </button>
          </div>
        </form>
      </div>

      <AnimatePresence mode="wait">
        {loading ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center justify-center py-12 space-y-4"
          >
            <div className="w-12 h-12 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
            <p className="text-slate-500 font-medium animate-pulse">Scanning area...</p>
          </motion.div>
        ) : error ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-red-50 dark:bg-red-900/20 border-2 border-red-100 dark:border-red-900/30 p-4 rounded-2xl flex items-start gap-3"
          >
            <AlertCircle className="w-6 h-6 text-red-500 shrink-0" />
            <p className="text-red-700 dark:text-red-400 font-medium">{error}</p>
          </motion.div>
        ) : results.length > 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-4 pb-24"
          >
            <h3 className="text-lg font-bold text-slate-700 dark:text-slate-300 px-2 flex items-center gap-2">
              <Users className="w-5 h-5" />
              Found {results.length} results
            </h3>
            {results.map((h) => (
              <motion.div
                key={h.household_id}
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                className="bg-white dark:bg-slate-900 p-5 rounded-3xl shadow-md border border-slate-100 dark:border-slate-800 group relative overflow-hidden"
              >
                {/* Background Decoration */}
                <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 blur-3xl -mr-16 -mt-16 group-hover:bg-blue-500/10 transition-colors" />
                
                <div className="flex justify-between items-start relative z-10">
                  <div className="flex-1 space-y-3">
                    <p className="text-lg font-bold text-slate-900 dark:text-white leading-tight">
                      {h.location_description}
                    </p>
                    
                    <div className="flex flex-wrap gap-2">
                      {h.landmark_tags.map((tag) => (
                        <span key={tag} className="bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 text-xs font-bold px-3 py-1 rounded-full uppercase tracking-wider">
                          {tag}
                        </span>
                      ))}
                    </div>

                    <div className="flex items-center gap-4">
                      <div className="flex -space-x-1">
                        {h.vulnerability_flags.has_child && <div className="p-1.5 bg-amber-100 dark:bg-amber-900/30 rounded-full text-amber-600 dark:text-amber-400" title="Children"><Baby className="w-4 h-4" /></div>}
                        {h.vulnerability_flags.has_elderly && <div className="p-1.5 bg-purple-100 dark:bg-purple-900/30 rounded-full text-purple-600 dark:text-purple-400" title="Elderly"><Users className="w-4 h-4" /></div>}
                        {h.vulnerability_flags.has_disabled && <div className="p-1.5 bg-blue-100 dark:bg-blue-900/30 rounded-full text-blue-600 dark:text-blue-400" title="Disabled"><Accessibility className="w-4 h-4" /></div>}
                      </div>

                      {h.crisis_frequency > 0 && (
                        <div className="text-xs font-bold text-red-500 bg-red-50 dark:bg-red-900/20 px-3 py-1 rounded-full border border-red-100 dark:border-red-900/30">
                          {h.crisis_frequency} reports this month
                        </div>
                      )}
                    </div>
                  </div>
                  
                  <button
                    onClick={() => onSelect(h)}
                    className="ml-4 bg-slate-900 dark:bg-white dark:text-slate-900 text-white p-3 rounded-2xl hover:bg-slate-800 transition-colors shadow-lg shadow-slate-900/10"
                  >
                    <UserCheck className="w-6 h-6" />
                  </button>
                </div>
              </motion.div>
            ))}
          </motion.div>
        ) : query ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-center py-12 space-y-6"
          >
            <div className="w-20 h-20 bg-slate-100 dark:bg-slate-800 rounded-full flex items-center justify-center mx-auto">
              <Search className="w-8 h-8 text-slate-400" />
            </div>
            <div className="space-y-2">
              <p className="text-slate-900 dark:text-white font-bold text-xl">No household found</p>
              <p className="text-slate-500 max-w-[240px] mx-auto text-sm">We couldn't find any households matching "{query}".</p>
            </div>
            <button
              onClick={onRegisterNew}
              className="bg-slate-900 dark:bg-white dark:text-slate-900 text-white font-bold px-8 py-4 rounded-2xl flex items-center justify-center gap-2 mx-auto active:scale-95 transition-transform"
            >
              <UserPlus className="w-5 h-5" />
              Register New Household
            </button>
          </motion.div>
        ) : (
          <div className="text-center py-12 space-y-6">
             <button
              onClick={onRegisterNew}
              className="bg-slate-900 dark:bg-white dark:text-slate-900 text-white font-bold px-8 py-4 rounded-2xl flex items-center justify-center gap-2 mx-auto active:scale-95 transition-transform"
            >
              <UserPlus className="w-5 h-5" />
              Register Household
            </button>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { NeedReportForm } from '../../components/field/NeedReportForm';
import { ChevronLeft, CheckCircle2, FileText, ArrowRight, AlertTriangle, Copy } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Household } from '../../types/household.types';
import { HouseholdAPI } from '../../api/endpoints';

export const NeedReportPage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const passedHousehold = location.state?.household as Household | undefined;
  const passedHouseholdId = location.state?.householdId as string | undefined;
  const [household, setHousehold] = useState<Household | null>(passedHousehold || null);
  const [loading, setLoading] = useState(!passedHousehold && !!passedHouseholdId);
  const [successData, setSuccessData] = useState<any>(null);

  useEffect(() => {
    if (!passedHousehold && passedHouseholdId) {
      HouseholdAPI.get(passedHouseholdId, true)
        .then((res) => setHousehold(res.data))
        .catch(() => navigate('/field/report'))
        .finally(() => setLoading(false));
    } else if (!passedHousehold && !passedHouseholdId) {
      navigate('/field/report');
    }
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-black flex items-center justify-center">
        <div className="w-10 h-10 border-4 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (!household && !successData) return null;

  const handleSuccess = (data: any) => {
    setSuccessData(data);
  };

  const statusLabel: Record<string, { icon: string; text: string; color: string }> = {
    auto_linked: { icon: '✅', text: 'Linked to existing household record', color: 'text-emerald-600' },
    review_required: { icon: '⏳', text: 'A coordinator will review this', color: 'text-amber-600' },
    new_household: { icon: '🆕', text: 'New household registered', color: 'text-blue-600' },
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-black p-4">
      <AnimatePresence mode="wait">
        {!successData ? (
          <motion.div
            key="form"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
          >
            <header className="flex items-center gap-4 mb-8 pt-4">
              <button
                onClick={() => navigate('/field/report')}
                className="p-3 bg-white dark:bg-slate-900 rounded-2xl shadow-sm text-slate-600 dark:text-slate-400 active:scale-90 transition-transform"
              >
                <ChevronLeft className="w-6 h-6" />
              </button>
              <div>
                <h1 className="text-2xl font-black text-slate-900 dark:text-white tracking-tight">Step 2 of 2</h1>
                <p className="text-slate-500 font-bold uppercase text-[10px] tracking-widest leading-none">Report Need</p>
              </div>
            </header>

            <NeedReportForm household={household!} onSuccess={handleSuccess} />
          </motion.div>
        ) : (
          <motion.div
            key="success"
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="min-h-screen flex flex-col items-center justify-center text-center p-6 space-y-8"
          >
            <div className="relative">
              <div className="absolute inset-0 bg-emerald-500/20 blur-3xl rounded-full scale-150" />
              <div className="relative w-24 h-24 bg-emerald-500 rounded-full flex items-center justify-center shadow-2xl shadow-emerald-500/40">
                <CheckCircle2 className="w-12 h-12 text-white" />
              </div>
            </div>

            <div className="space-y-2">
              <h2 className="text-3xl font-black text-slate-900 dark:text-white">Report Submitted</h2>
              {statusLabel[successData.household_status] && (
                <p className={`font-bold text-sm ${statusLabel[successData.household_status].color}`}>
                  {statusLabel[successData.household_status].icon} {statusLabel[successData.household_status].text}
                </p>
              )}
            </div>

            <div className="bg-white dark:bg-slate-900 rounded-3xl p-6 shadow-xl border border-slate-100 dark:border-slate-800 w-full max-w-sm space-y-4">
              <div className="flex justify-between items-center text-xs">
                <span className="font-black text-slate-400 uppercase tracking-widest">Need ID</span>
                <span className="font-mono font-bold text-slate-900 dark:text-white bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-lg">{successData.need_id?.slice(0, 8)}...</span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="font-black text-slate-400 uppercase tracking-widest">Status</span>
                <span className="bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 font-black px-3 py-1 rounded-full uppercase tracking-tighter">
                  {successData.household_status || 'submitted'}
                </span>
              </div>
              {successData.is_duplicate && (
                <div className="pt-4 border-t border-slate-100 dark:border-slate-800 flex items-start gap-3 text-left">
                  <Copy className="w-5 h-5 text-amber-500 shrink-0" />
                  <p className="text-[10px] font-bold text-slate-500 leading-normal">
                    Similar report already exists — no new record created.
                  </p>
                </div>
              )}
              {successData.routed_to_review && (
                <div className="pt-4 border-t border-slate-100 dark:border-slate-800 flex items-start gap-3 text-left">
                  <FileText className="w-5 h-5 text-amber-500 shrink-0" />
                  <p className="text-[10px] font-bold text-slate-500 leading-normal">
                    Sent to review queue for verification. A coordinator will process this shortly.
                  </p>
                </div>
              )}
            </div>

            <div className="space-y-3 w-full max-w-sm">
              <button
                onClick={() => {
                  setSuccessData(null);
                  // Stay on same page with same household for another report
                }}
                className="w-full bg-slate-900 dark:bg-white dark:text-slate-900 text-white font-black py-5 rounded-2xl flex items-center justify-center gap-2 active:scale-95 transition-transform"
              >
                Report Another Need
              </button>
              <button
                onClick={() => navigate('/field')}
                className="w-full bg-white dark:bg-slate-900 text-slate-900 dark:text-white font-black py-5 rounded-2xl border-2 border-slate-100 dark:border-slate-800 shadow-xl shadow-slate-900/5 flex items-center justify-center gap-2 active:scale-95 transition-transform"
              >
                Done
                <ArrowRight className="w-5 h-5" />
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default NeedReportPage;

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { HouseholdRegistrationForm } from '../../components/field/HouseholdRegistrationForm';
import { ChevronLeft } from 'lucide-react';
import { motion } from 'framer-motion';

export const HouseholdRegistrationPage: React.FC = () => {
  const navigate = useNavigate();

  const handleSuccess = (householdId: string) => {
    // Navigate to step 2 (reporting need) with the new household ID
    // NeedReportPage will fetch the full household data
    navigate('/field/report/need', { state: { householdId } });
  };

  const handleCancel = () => {
    navigate('/field/report');
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-black p-4 pb-20">
      <header className="flex items-center gap-4 mb-8 pt-4">
        <button 
          onClick={handleCancel}
          className="p-3 bg-white dark:bg-slate-900 rounded-2xl shadow-sm text-slate-600 dark:text-slate-400 active:scale-90 transition-transform"
        >
          <ChevronLeft className="w-6 h-6" />
        </button>
        <div>
          <h1 className="text-2xl font-black text-slate-900 dark:text-white tracking-tight">New Household</h1>
          <p className="text-slate-500 font-bold uppercase text-[10px] tracking-widest leading-none">Registration</p>
        </div>
      </header>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <HouseholdRegistrationForm onSuccess={handleSuccess} onCancel={handleCancel} />
      </motion.div>
    </div>
  );
};

export default HouseholdRegistrationPage;

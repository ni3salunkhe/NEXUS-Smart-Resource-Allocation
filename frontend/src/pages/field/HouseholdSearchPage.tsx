import React from 'react';
import { useNavigate } from 'react-router-dom';
import { HouseholdLookup } from '../../components/field/HouseholdLookup';
import { Household } from '../../types/household.types';
import { motion } from 'framer-motion';
import { ChevronLeft } from 'lucide-react';

export const HouseholdSearchPage: React.FC = () => {
  const navigate = useNavigate();

  const handleSelect = (h: Household) => {
    // Navigate to step 2 with household id
    navigate('/field/report/need', { state: { household: h } });
  };

  const handleRegisterNew = () => {
    navigate('/field/households/new');
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-black p-4 pb-20">
      <header className="flex items-center gap-4 mb-8 pt-4">
        <button 
          onClick={() => navigate('/field')}
          className="p-3 bg-white dark:bg-slate-900 rounded-2xl shadow-sm text-slate-600 dark:text-slate-400 active:scale-90 transition-transform"
        >
          <ChevronLeft className="w-6 h-6" />
        </button>
        <div>
          <h1 className="text-2xl font-black text-slate-900 dark:text-white tracking-tight">Step 1 of 2</h1>
          <p className="text-slate-500 font-bold uppercase text-[10px] tracking-widest leading-none">Find Household</p>
        </div>
      </header>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <HouseholdLookup onSelect={handleSelect} onRegisterNew={handleRegisterNew} />
      </motion.div>
    </div>
  );
};

export default HouseholdSearchPage;

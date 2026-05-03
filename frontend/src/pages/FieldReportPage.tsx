import React, { useState } from 'react';
import { Search, MapPin, Plus, ChevronRight, ChevronLeft, Send, CheckCircle2, AlertCircle, Baby, Users, Accessibility, UserCheck, Heart } from 'lucide-react';
import { HouseholdAPI, NeedAPI, IdentityAPI } from '../api/endpoints';
import { toast } from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/auth.store';

type Step = 'lookup' | 'report' | 'success';

export function FieldReportPage() {
  const [step, setStep] = useState<Step>('lookup');
  const [searchQuery, setSearchQuery] = useState('');
  const [households, setHouseholds] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [selectedHousehold, setSelectedHousehold] = useState<any>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [lastResult, setLastResult] = useState<any>(null);

  const { tenant_id } = useAuthStore();
  const navigate = useNavigate();

  // Need form state
  const [category, setCategory] = useState('food');
  const [description, setDescription] = useState('');
  const [beneficiaryCount, setBeneficiaryCount] = useState(1);
  const [isUrgent, setIsUrgent] = useState(false);
  const [language, setLanguage] = useState('en');

  const CATEGORIES = [
    { id: 'food', label: 'Food', icon: '🍚', color: 'bg-orange-100 text-orange-600' },
    { id: 'health', label: 'Health', icon: '🏥', color: 'bg-red-100 text-red-600' },
    { id: 'shelter', label: 'Shelter', icon: '🏠', color: 'bg-blue-100 text-blue-600' },
    { id: 'education', label: 'Education', icon: '📚', color: 'bg-purple-100 text-purple-600' },
    { id: 'livelihood', label: 'Livelihood', icon: '💼', color: 'bg-green-100 text-green-600' },
    { id: 'water', label: 'Water', icon: '💧', color: 'bg-sky-100 text-sky-600' },
    { id: 'hygiene', label: 'Hygiene', icon: '🧹', color: 'bg-teal-100 text-teal-600' },
    { id: 'mental_health', label: 'Mental Health', icon: '🧠', color: 'bg-indigo-100 text-indigo-600' },
    { id: 'legal', label: 'Legal', icon: '⚖️', color: 'bg-slate-100 text-slate-600' },
    { id: 'other', label: 'Other', icon: '📄', color: 'bg-gray-100 text-gray-600' },
  ];

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!searchQuery && !navigator.geolocation) return;

    setIsSearching(true);
    try {
      const res = await HouseholdAPI.search({
        query: searchQuery,
        limit: 10
      });
      setHouseholds(res.data || []);
    } catch (err) {
      toast.error('Search failed');
    } finally {
      setIsSearching(false);
    }
  };

  const handleUseGPS = () => {
    if (!navigator.geolocation) {
      toast.error('GPS not supported');
      return;
    }

    navigator.geolocation.getCurrentPosition(async (pos) => {
      setIsSearching(true);
      try {
        const res = await HouseholdAPI.search({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          radius_m: 200,
          limit: 10
        });
        setHouseholds(res.data || []);
      } catch (err) {
        toast.error('GPS search failed');
      } finally {
        setIsSearching(false);
      }
    }, (err) => {
      toast.error('Failed to get location');
    });
  };

  const handleSelectHousehold = async (hh: any) => {
    setSelectedHousehold(hh);
    try {
      await IdentityAPI.resolve({
        known_household_id: hh.household_id || hh.id,
        tenant_id
      });
      setStep('report');
    } catch (err) {
      toast.error('Failed to resolve household context');
    }
  };

  const handleSubmitReport = async () => {
    if (!description) {
      toast.error('Description required');
      return;
    }

    setIsSubmitting(true);
    try {
      const finalDescription = isUrgent ? `URGENT: ${description}` : description;
      const res = await NeedAPI.ingestMobile({
        category,
        description: finalDescription,
        known_household_id: selectedHousehold.household_id || selectedHousehold.id,
        beneficiary_count: beneficiaryCount,
        language,
        vulnerability_flags: selectedHousehold.vulnerability_flags || {}
      });
      setLastResult(res.data);
      setStep('success');
      toast.success('Report submitted successfully');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Submission failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-md mx-auto h-full flex flex-col bg-slate-50 overflow-hidden">
      {/* Header */}
      <div className="bg-white px-6 py-4 border-b border-slate-200 sticky top-0 z-10">
        <h1 className="text-xl font-bold text-slate-900">
          {step === 'lookup' && 'Find Household'}
          {step === 'report' && 'Report Need'}
          {step === 'success' && 'Success'}
        </h1>
        <div className="flex gap-1 mt-2">
          <div className={`h-1 flex-1 rounded-full ${step === 'lookup' ? 'bg-brand-600' : 'bg-slate-200'}`} />
          <div className={`h-1 flex-1 rounded-full ${step === 'report' ? 'bg-brand-600' : 'bg-slate-200'}`} />
          <div className={`h-1 flex-1 rounded-full ${step === 'success' ? 'bg-brand-600' : 'bg-slate-200'}`} />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {step === 'lookup' && (
          <div className="space-y-6">
            <form onSubmit={handleSearch} className="space-y-3">
              <div className="relative">
                <Search className="absolute left-3 top-3 w-5 h-5 text-slate-400" />
                <input
                  type="text"
                  className="w-full bg-white border border-slate-200 rounded-2xl py-3 pl-10 pr-4 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-all shadow-sm"
                  placeholder="Location description or landmark..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              <div className="flex gap-3">
                <button
                  type="submit"
                  disabled={isSearching}
                  className="flex-1 bg-brand-600 text-white py-3 rounded-2xl font-bold hover:bg-brand-700 transition-all shadow-md active:scale-95 disabled:opacity-50"
                >
                  Search
                </button>
                <button
                  type="button"
                  onClick={handleUseGPS}
                  className="px-4 bg-white border border-slate-200 text-slate-700 rounded-2xl hover:bg-slate-50 transition-all shadow-sm active:scale-95"
                >
                  <MapPin className="w-5 h-5" />
                </button>
              </div>
            </form>

            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <h2 className="text-xs font-bold text-slate-500 uppercase tracking-wider">Results</h2>
                <button 
                  onClick={() => navigate('/field/households/new')}
                  className="text-xs font-bold text-brand-600 flex items-center gap-1 hover:underline"
                >
                  <Plus className="w-3 h-3" /> Register New
                </button>
              </div>

              {isSearching ? (
                <div className="flex flex-col items-center py-12 text-slate-400 gap-3">
                  <div className="w-8 h-8 border-4 border-brand-200 border-t-brand-600 rounded-full animate-spin" />
                  <p className="text-sm font-medium">Searching households...</p>
                </div>
              ) : households.length > 0 ? (
                households.map((hh) => (
                  <button
                    key={hh.household_id || hh.id}
                    onClick={() => handleSelectHousehold(hh)}
                    className="w-full bg-white p-4 rounded-2xl border border-slate-200 shadow-sm hover:border-brand-300 hover:shadow-md transition-all text-left space-y-3"
                  >
                    <div>
                      <p className="text-sm font-bold text-slate-900">{hh.location_description || 'Unknown Location'}</p>
                      <div className="flex flex-wrap gap-1 mt-2">
                        {hh.landmark_tags?.map((tag: string) => (
                          <span key={tag} className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full font-bold">
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-xs font-medium text-slate-500">
                      <div className="flex gap-2">
                        {hh.vulnerability_flags?.has_child && <Baby className="w-4 h-4 text-blue-500" />}
                        {hh.vulnerability_flags?.has_elderly && <Users className="w-4 h-4 text-purple-500" />}
                        {hh.vulnerability_flags?.has_disabled && <Accessibility className="w-4 h-4 text-orange-500" />}
                      </div>
                      <div className="flex items-center gap-1 text-slate-400">
                        <span>Reported {hh.total_needs_reported || 0}x</span>
                        <ChevronRight className="w-4 h-4" />
                      </div>
                    </div>
                  </button>
                ))
              ) : searchQuery && (
                <div className="text-center py-12 space-y-4">
                  <p className="text-sm text-slate-400">No matching households found.</p>
                  <button
                    onClick={() => navigate('/field/households/new')}
                    className="bg-brand-50 text-brand-700 px-6 py-3 rounded-2xl font-bold hover:bg-brand-100 transition-all"
                  >
                    Register New Household
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {step === 'report' && selectedHousehold && (
          <div className="space-y-6">
            {/* Household Summary */}
            <div className="bg-brand-900 text-white p-5 rounded-3xl shadow-xl space-y-3">
              <div className="flex justify-between items-start">
                <div className="space-y-1">
                  <p className="text-[10px] font-black uppercase tracking-[0.2em] opacity-60">Reporting for</p>
                  <p className="font-bold text-lg leading-tight">{selectedHousehold.location_description}</p>
                </div>
                <button 
                  onClick={() => setStep('lookup')}
                  className="p-2 bg-white/10 rounded-full hover:bg-white/20 transition-all"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
              </div>
              <div className="flex gap-4 text-xs font-bold bg-white/10 p-3 rounded-2xl">
                <div className="flex items-center gap-1.5">
                  <Users className="w-4 h-4 opacity-70" />
                  <span>HH-{selectedHousehold.household_id?.slice(-5) || 'NEW'}</span>
                </div>
                {selectedHousehold.crisis_frequency > 0 && (
                  <div className="flex items-center gap-1.5 text-amber-300">
                    <AlertCircle className="w-4 h-4" />
                    <span>Active {selectedHousehold.crisis_frequency}x this month</span>
                  </div>
                )}
              </div>
            </div>

            {/* Need Form */}
            <div className="space-y-6">
              <div className="space-y-3">
                <label className="text-xs font-black text-slate-400 uppercase tracking-widest">Select Category</label>
                <div className="grid grid-cols-5 gap-2">
                  {CATEGORIES.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => setCategory(c.id)}
                      className={`flex flex-col items-center gap-1.5 p-3 rounded-2xl transition-all border-2 ${
                        category === c.id 
                          ? 'border-brand-600 bg-brand-50 shadow-sm scale-105' 
                          : 'border-transparent bg-white hover:bg-slate-50'
                      }`}
                    >
                      <span className="text-xl">{c.icon}</span>
                      <span className={`text-[9px] font-black uppercase tracking-tighter text-center ${
                        category === c.id ? 'text-brand-700' : 'text-slate-400'
                      }`}>
                        {c.id.replace('_', ' ')}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-3">
                <div className="flex justify-between items-end">
                  <label className="text-xs font-black text-slate-400 uppercase tracking-widest">Description</label>
                  <div className="flex gap-1">
                    {['en', 'hi', 'mr', 'ta'].map(lang => (
                      <button
                        key={lang}
                        onClick={() => setLanguage(lang)}
                        className={`w-6 h-6 rounded-md text-[10px] font-bold uppercase transition-all ${
                          language === lang ? 'bg-brand-600 text-white shadow-sm' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
                        }`}
                      >
                        {lang}
                      </button>
                    ))}
                  </div>
                </div>
                <textarea
                  className="w-full bg-white border border-slate-200 rounded-2xl p-4 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500 outline-none transition-all shadow-sm"
                  rows={4}
                  placeholder="Describe the need..."
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-3">
                  <label className="text-xs font-black text-slate-400 uppercase tracking-widest">People Affected</label>
                  <div className="flex items-center gap-3 bg-white border border-slate-200 rounded-2xl p-2 px-4 shadow-sm">
                    <button 
                      onClick={() => setBeneficiaryCount(Math.max(1, beneficiaryCount - 1))}
                      className="w-8 h-8 flex items-center justify-center bg-slate-100 rounded-xl text-slate-600 active:scale-90"
                    >
                      -
                    </button>
                    <span className="flex-1 text-center font-bold text-slate-900">{beneficiaryCount}</span>
                    <button 
                      onClick={() => setBeneficiaryCount(beneficiaryCount + 1)}
                      className="w-8 h-8 flex items-center justify-center bg-slate-100 rounded-xl text-slate-600 active:scale-90"
                    >
                      +
                    </button>
                  </div>
                </div>
                <div className="space-y-3">
                  <label className="text-xs font-black text-slate-400 uppercase tracking-widest">Urgency</label>
                  <button
                    onClick={() => setIsUrgent(!isUrgent)}
                    className={`w-full h-[50px] rounded-2xl font-bold text-sm flex items-center justify-center gap-2 transition-all shadow-sm ${
                      isUrgent 
                        ? 'bg-red-600 text-white shadow-red-200' 
                        : 'bg-white border border-slate-200 text-slate-400'
                    }`}
                  >
                    <AlertCircle className={`w-4 h-4 ${isUrgent ? 'animate-pulse' : ''}`} />
                    {isUrgent ? 'URGENT' : 'NORMAL'}
                  </button>
                </div>
              </div>

              <button
                onClick={handleSubmitReport}
                disabled={isSubmitting}
                className="w-full bg-brand-600 text-white py-4 rounded-3xl font-black uppercase tracking-widest text-sm flex items-center justify-center gap-3 shadow-xl hover:bg-brand-700 hover:shadow-2xl transition-all active:scale-95 disabled:opacity-50 mt-4"
              >
                {isSubmitting ? (
                  <div className="w-5 h-5 border-2 border-white/20 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    <Send className="w-5 h-5" />
                    Submit Report
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {step === 'success' && lastResult && (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-8 animate-in fade-in zoom-in duration-500">
            <div className="relative">
              <div className="absolute inset-0 bg-brand-200 rounded-full blur-3xl opacity-30 animate-pulse" />
              <div className="relative bg-white p-6 rounded-full shadow-2xl">
                <CheckCircle2 className="w-16 h-16 text-brand-600" />
              </div>
            </div>
            
            <div className="space-y-2">
              <h2 className="text-2xl font-black text-slate-900">Report Received!</h2>
              <p className="text-slate-500 text-sm max-w-[250px] mx-auto">
                Need has been logged and sent to the coordinator queue.
              </p>
            </div>

            <div className="w-full space-y-3">
              <div className="bg-white border border-slate-200 rounded-2xl p-4 text-left space-y-2 shadow-sm">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-400 font-bold uppercase">Status</span>
                  <span className={`px-2 py-0.5 rounded-full font-black uppercase tracking-tighter ${
                    lastResult.household_status === 'new_household' ? 'bg-blue-100 text-blue-600' : 'bg-green-100 text-green-600'
                  }`}>
                    {lastResult.household_status?.replace('_', ' ')}
                  </span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-slate-400 font-bold uppercase">Need ID</span>
                  <span className="font-mono text-slate-600">{lastResult.need_id?.slice(0, 8)}...</span>
                </div>
                {lastResult.is_duplicate && (
                  <div className="flex items-center gap-2 text-amber-600 bg-amber-50 p-2 rounded-xl text-[10px] font-bold">
                    <AlertCircle className="w-3 h-3" />
                    Similar report already exists
                  </div>
                )}
              </div>
            </div>

            <div className="w-full space-y-3 pt-4">
              <button
                onClick={() => {
                  setStep('lookup');
                  setHouseholds([]);
                  setSearchQuery('');
                  setSelectedHousehold(null);
                  setDescription('');
                  setIsUrgent(false);
                }}
                className="w-full bg-slate-900 text-white py-4 rounded-2xl font-bold hover:bg-slate-800 transition-all shadow-lg active:scale-95"
              >
                Report Another Need
              </button>
              <button
                onClick={() => navigate('/field')}
                className="w-full bg-white text-slate-600 py-4 rounded-2xl font-bold border border-slate-200 hover:bg-slate-50 transition-all active:scale-95"
              >
                Return Home
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

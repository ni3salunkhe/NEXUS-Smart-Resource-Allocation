import React, { useState } from 'react';
import { useForm, useFieldArray } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  MapPin, Navigation, UserPlus, Trash2, CheckCircle2, 
  ChevronRight, ChevronLeft, ShieldCheck, Info
} from 'lucide-react';
import { HouseholdAPI } from '../../api/endpoints';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const memberSchema = z.object({
  role_in_household: z.enum(['head', 'spouse', 'child', 'parent', 'dependent', 'other']),
  age_bracket: z.enum(['infant', 'child', 'youth', 'adult', 'elderly']),
  gender: z.string().optional(),
  is_primary_contact: z.boolean().default(false),
  vulnerability_flags: z.object({
    disabled: z.boolean().default(false),
    chronic_illness: z.boolean().default(false),
    pregnant: z.boolean().default(false),
    malnourished: z.boolean().default(false),
    mental_health: z.boolean().default(false),
  })
});

const registrationSchema = z.object({
  location: z.object({
    latitude: z.number(),
    longitude: z.number(),
    description: z.string().min(10, "Description too short"),
    landmarks: z.array(z.string()).min(1, "At least one landmark required"),
    confidence: z.number().default(1.0),
  }),
  ward_id: z.string().min(1, "Ward required"),
  dwelling_type: z.enum(['permanent', 'semi-permanent', 'temporary', 'open-space']),
  economic_tier: z.enum(['below_poverty', 'marginal', 'low', 'medium']),
  members: z.array(memberSchema).min(1, "At least one member required"),
  consent: z.object({
    language: z.enum(['en', 'hi', 'mr', 'ta']),
    method: z.enum(['verbal_witnessed', 'signed_form', 'digital_app']),
    confirmed: z.literal(true, {
      errorMap: () => ({ message: "Consent is required" }),
    }),
  })
});

type RegistrationData = z.infer<typeof registrationSchema>;

interface HouseholdRegistrationFormProps {
  onSuccess: (householdId: string) => void;
  onCancel: () => void;
}

export const HouseholdRegistrationForm: React.FC<HouseholdRegistrationFormProps> = ({ onSuccess, onCancel }) => {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [newLandmark, setNewLandmark] = useState('');

  const { register, control, handleSubmit, watch, setValue, formState: { errors } } = useForm<RegistrationData>({
    resolver: zodResolver(registrationSchema),
    defaultValues: {
      location: { latitude: 0, longitude: 0, landmarks: [], confidence: 1.0 },
      members: [{ 
        role_in_household: 'head', 
        age_bracket: 'adult', 
        is_primary_contact: true,
        vulnerability_flags: { disabled: false, chronic_illness: false, pregnant: false, malnourished: false, mental_health: false }
      }],
      consent: { language: 'hi', method: 'verbal_witnessed' },
      dwelling_type: 'temporary',
      economic_tier: 'below_poverty'
    }
  });

  const { fields, append, remove } = useFieldArray({
    control,
    name: "members"
  });

  const onSubmit = async (data: RegistrationData) => {
    setLoading(true);
    try {
      // 1. Create Household
      const res = await HouseholdAPI.create({
        ward_id: data.ward_id,
        location: data.location,
        dwelling_type: data.dwelling_type,
        economic_tier: data.economic_tier,
        members: data.members
      });
      
      const householdId = res.data.household_id;

      // 2. Add Consent
      await HouseholdAPI.addConsent(householdId, {
        consent_type: 'general_intake',
        scope: 'full_service',
        collection_method: data.consent.method,
        language_used: data.consent.language
      });

      onSuccess(householdId);
    } catch (err) {
      console.error(err);
      alert('Registration failed. Check network.');
    } finally {
      setLoading(false);
    }
  };

  const handleGPS = () => {
    navigator.geolocation.getCurrentPosition((pos) => {
      setValue('location.latitude', pos.coords.latitude);
      setValue('location.longitude', pos.coords.longitude);
      setValue('location.confidence', pos.coords.accuracy / 100);
    });
  };

  const addLandmark = () => {
    if (!newLandmark.trim()) return;
    const current = watch('location.landmarks');
    setValue('location.landmarks', [...current, newLandmark.trim()]);
    setNewLandmark('');
  };

  const nextStep = () => setStep(s => s + 1);
  const prevStep = () => setStep(s => s - 1);

  const landmarks = watch('location.landmarks');
  const lat = watch('location.latitude');
  const lng = watch('location.longitude');

  return (
    <div className="max-w-xl mx-auto space-y-8">
      {/* Progress Bar */}
      <div className="flex justify-between px-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex flex-col items-center gap-2">
            <div className={cn(
              "w-10 h-10 rounded-2xl flex items-center justify-center font-bold transition-all duration-500",
              step === i ? "bg-blue-600 text-white shadow-lg shadow-blue-500/40 scale-110" : 
              step > i ? "bg-emerald-500 text-white shadow-lg shadow-emerald-500/20" : "bg-slate-200 dark:bg-slate-800 text-slate-400"
            )}>
              {step > i ? <CheckCircle2 className="w-6 h-6" /> : i}
            </div>
            <span className={cn(
              "text-[10px] font-black uppercase tracking-tighter",
              step === i ? "text-blue-600" : "text-slate-400"
            )}>
              {i === 1 ? 'Location' : i === 2 ? 'Members' : 'Consent'}
            </span>
          </div>
        ))}
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        <AnimatePresence mode="wait">
          {step === 1 && (
            <motion.div
              key="step1"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-6"
            >
              <div className="bg-white dark:bg-slate-900 rounded-3xl p-6 shadow-xl border border-slate-100 dark:border-slate-800 space-y-6">
                <div className="space-y-4">
                  <label className="text-sm font-black uppercase tracking-widest text-slate-400">Where is it?</label>
                  <div className="flex gap-3">
                    <div className="flex-1 bg-slate-50 dark:bg-slate-800 p-4 rounded-2xl border-2 border-slate-100 dark:border-slate-700">
                       <p className="text-[10px] font-bold text-slate-400 uppercase">GPS Coordinates</p>
                       <p className="text-sm font-mono font-bold text-slate-900 dark:text-white">
                         {lat ? `${lat.toFixed(4)}, ${lng.toFixed(4)}` : 'Not captured'}
                       </p>
                    </div>
                    <button
                      type="button"
                      onClick={handleGPS}
                      className="bg-blue-600 text-white p-4 rounded-2xl shadow-lg shadow-blue-500/30 active:scale-95 transition-transform"
                    >
                      <Navigation className="w-6 h-6" />
                    </button>
                  </div>
                </div>

                <div className="space-y-4">
                  <label className="text-sm font-black uppercase tracking-widest text-slate-400">Description</label>
                  <textarea
                    {...register('location.description')}
                    placeholder='e.g. "Third house on left after the temple, blue door"'
                    className="w-full bg-slate-50 dark:bg-slate-800/50 border-2 border-slate-100 dark:border-slate-800 rounded-2xl p-4 text-slate-900 dark:text-white placeholder:text-slate-400 focus:outline-none focus:border-blue-500 transition-all min-h-[100px] font-medium"
                  />
                  {errors.location?.description && <p className="text-red-500 text-xs font-bold">{errors.location.description.message}</p>}
                </div>

                <div className="space-y-4">
                  <label className="text-sm font-black uppercase tracking-widest text-slate-400">Landmarks (At least 1)</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      className="flex-1 bg-slate-50 dark:bg-slate-800/50 border-2 border-slate-100 dark:border-slate-800 rounded-2xl px-4 py-3 text-sm"
                      placeholder="Add landmark..."
                      value={newLandmark}
                      onChange={(e) => setNewLandmark(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addLandmark())}
                    />
                    <button
                      type="button"
                      onClick={addLandmark}
                      className="bg-slate-900 dark:bg-white dark:text-slate-900 text-white p-3 rounded-2xl active:scale-90 transition-transform"
                    >
                      <UserPlus className="w-5 h-5" />
                    </button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {landmarks.map((l, i) => (
                      <span key={i} className="bg-blue-50 dark:bg-blue-900/40 text-blue-600 dark:text-blue-300 px-4 py-2 rounded-xl text-xs font-bold border border-blue-100 dark:border-blue-800 flex items-center gap-2">
                        {l}
                        <Trash2 className="w-3 h-3 cursor-pointer" onClick={() => {
                          const newer = [...landmarks];
                          newer.splice(i, 1);
                          setValue('location.landmarks', newer);
                        }} />
                      </span>
                    ))}
                  </div>
                   {errors.location?.landmarks && <p className="text-red-500 text-xs font-bold">{errors.location.landmarks.message}</p>}
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-[10px] font-black uppercase text-slate-400">Ward ID</label>
                    <input
                      {...register('ward_id')}
                      className="w-full bg-slate-50 dark:bg-slate-800 rounded-xl px-4 py-3 text-sm font-bold border-2 border-slate-100 dark:border-slate-800"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-[10px] font-black uppercase text-slate-400">Dwelling</label>
                    <select
                      {...register('dwelling_type')}
                      className="w-full bg-slate-50 dark:bg-slate-800 rounded-xl px-4 py-3 text-sm font-bold border-2 border-slate-100 dark:border-slate-800 appearance-none"
                    >
                      <option value="permanent">Permanent</option>
                      <option value="semi-permanent">Semi-Perm</option>
                      <option value="temporary">Temporary</option>
                      <option value="open-space">Open Space</option>
                    </select>
                  </div>
                </div>

                <div className="space-y-4">
                  <label className="text-sm font-black uppercase tracking-widest text-slate-400">Economic Tier</label>
                  <div className="grid grid-cols-2 gap-2">
                    {['below_poverty', 'marginal', 'low', 'medium'].map((tier) => (
                      <button
                        key={tier}
                        type="button"
                        onClick={() => setValue('economic_tier', tier as any)}
                        className={cn(
                          "py-3 rounded-xl text-xs font-bold transition-all border-2",
                          watch('economic_tier') === tier 
                            ? "bg-blue-600 border-blue-600 text-white shadow-lg shadow-blue-500/20" 
                            : "bg-white dark:bg-slate-800 border-slate-100 dark:border-slate-700 text-slate-500"
                        )}
                      >
                        {tier.replace('_', ' ').toUpperCase()}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={nextStep}
                className="w-full bg-slate-900 dark:bg-white dark:text-slate-900 text-white font-black py-5 rounded-3xl shadow-xl flex items-center justify-center gap-2 active:scale-[0.98] transition-transform"
              >
                Next: Add Members
                <ChevronRight className="w-5 h-5" />
              </button>
            </motion.div>
          )}

          {step === 2 && (
            <motion.div
              key="step2"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-6"
            >
              <div className="space-y-4 pb-4">
                {fields.map((field, index) => (
                  <div key={field.id} className="bg-white dark:bg-slate-900 rounded-3xl p-6 shadow-xl border border-slate-100 dark:border-slate-800 relative overflow-hidden group">
                    <div className="absolute top-0 left-0 w-1 h-full bg-blue-500" />
                    <div className="flex justify-between items-center mb-6">
                      <h4 className="font-black text-slate-900 dark:text-white uppercase tracking-tighter">Member #{index + 1}</h4>
                      {fields.length > 1 && (
                        <button type="button" onClick={() => remove(index)} className="text-red-500 p-2 hover:bg-red-50 rounded-xl transition-colors">
                          <Trash2 className="w-5 h-5" />
                        </button>
                      )}
                    </div>

                    <div className="grid grid-cols-2 gap-4 mb-6">
                      <div className="space-y-2">
                        <label className="text-[10px] font-black tracking-widest text-slate-400 uppercase">Role</label>
                        <select
                          {...register(`members.${index}.role_in_household`)}
                          className="w-full bg-slate-50 dark:bg-slate-800 rounded-xl p-3 text-sm font-bold border-2 border-slate-100 dark:border-slate-700"
                        >
                          <option value="head">Head</option>
                          <option value="spouse">Spouse</option>
                          <option value="child">Child</option>
                          <option value="parent">Parent</option>
                          <option value="dependent">Dependent</option>
                          <option value="other">Other</option>
                        </select>
                      </div>
                      <div className="space-y-2">
                        <label className="text-[10px] font-black tracking-widest text-slate-400 uppercase">Age</label>
                        <select
                          {...register(`members.${index}.age_bracket`)}
                          className="w-full bg-slate-50 dark:bg-slate-800 rounded-xl p-3 text-sm font-bold border-2 border-slate-100 dark:border-slate-700"
                        >
                          <option value="infant">Infant (0-2)</option>
                          <option value="child">Child (3-12)</option>
                          <option value="youth">Youth (13-24)</option>
                          <option value="adult">Adult (25-60)</option>
                          <option value="elderly">Elderly (60+)</option>
                        </select>
                      </div>
                    </div>

                    <div className="space-y-3">
                      <label className="text-[10px] font-black tracking-widest text-slate-400 uppercase">Vulnerability</label>
                      <div className="grid grid-cols-2 gap-2">
                        {[
                          { id: 'disabled', label: 'Disabled' },
                          { id: 'chronic_illness', label: 'Chronic' },
                          { id: 'pregnant', label: 'Pregnant' },
                          { id: 'malnourished', label: 'Malnourished' },
                          { id: 'mental_health', label: 'Mental Health' },
                        ].map((v) => (
                           <label key={v.id} className={cn(
                             "flex items-center gap-2 p-3 rounded-xl border-2 transition-all cursor-pointer",
                             watch(`members.${index}.vulnerability_flags.${v.id}` as any) 
                                ? "bg-amber-50 dark:bg-amber-900/20 border-amber-500 text-amber-700 dark:text-amber-400 shadow-lg shadow-amber-500/10" 
                                : "bg-slate-50 dark:bg-slate-800 border-transparent text-slate-500"
                           )}>
                             <input
                               type="checkbox"
                               className="hidden"
                               {...register(`members.${index}.vulnerability_flags.${v.id}` as any)}
                             />
                             <span className="text-[10px] font-black uppercase whitespace-nowrap">{v.label}</span>
                           </label>
                        ))}
                      </div>
                    </div>
                  </div>
                ))}

                <button
                  type="button"
                  onClick={() => append({ role_in_household: 'other', age_bracket: 'adult', is_primary_contact: false, vulnerability_flags: { disabled: false, chronic_illness: false, pregnant: false, malnourished: false, mental_health: false } })}
                  className="w-full border-2 border-dashed border-slate-300 dark:border-slate-700 py-6 rounded-3xl text-slate-400 font-bold flex items-center justify-center gap-2 hover:border-blue-500 hover:text-blue-500 transition-all"
                >
                  <UserPlus className="w-5 h-5" />
                  Add Household Member
                </button>
              </div>

              <div className="flex gap-4">
                <button
                  type="button"
                  onClick={prevStep}
                  className="flex-1 bg-white dark:bg-slate-900 text-slate-900 dark:text-white font-black py-5 rounded-3xl border-2 border-slate-100 dark:border-slate-800 active:scale-95 transition-transform"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={nextStep}
                  className="flex-[2] bg-slate-900 dark:bg-white dark:text-slate-900 text-white font-black py-5 rounded-3xl shadow-xl flex items-center justify-center gap-2 active:scale-95 transition-transform"
                >
                  Next: Consent
                  <ChevronRight className="w-5 h-5" />
                </button>
              </div>
            </motion.div>
          )}

          {step === 3 && (
            <motion.div
              key="step3"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-6"
            >
              <div className="bg-white dark:bg-slate-900 rounded-3xl p-8 shadow-xl border border-slate-100 dark:border-slate-800 space-y-8">
                <div className="flex justify-center">
                   <div className="w-20 h-20 bg-blue-50 dark:bg-blue-900/20 rounded-full flex items-center justify-center">
                     <ShieldCheck className="w-10 h-10 text-blue-600 dark:text-blue-400" />
                   </div>
                </div>

                <div className="text-center space-y-2">
                  <h3 className="text-xl font-black text-slate-900 dark:text-white">Consent Collection</h3>
                  <p className="text-slate-500 text-sm">Required for assessment under DPDP Act 2023.</p>
                </div>

                <div className="space-y-6">
                  <div className="space-y-3">
                     <label className="text-[10px] font-black uppercase text-slate-400 tracking-widest">Language Used</label>
                     <div className="flex gap-2">
                       {['en', 'hi', 'mr', 'ta'].map((lang) => (
                         <button
                           key={lang}
                           type="button"
                           onClick={() => setValue('consent.language', lang as any)}
                           className={cn(
                             "flex-1 py-3 rounded-xl font-black text-xs transition-all",
                             watch('consent.language') === lang ? "bg-blue-600 text-white" : "bg-slate-100 dark:bg-slate-800 text-slate-400"
                           )}
                         >
                           {lang.toUpperCase()}
                         </button>
                       ))}
                     </div>
                  </div>

                  <div className="space-y-3">
                     <label className="text-[10px] font-black uppercase text-slate-400 tracking-widest">Method</label>
                     <div className="space-y-2">
                       {[
                         { id: 'verbal_witnessed', label: 'Verbal (Witnessed)' },
                         { id: 'digital_app', label: 'Digital via App' },
                         { id: 'signed_form', label: 'Signed Form' },
                       ].map((m) => (
                         <button
                           key={m.id}
                           type="button"
                           onClick={() => setValue('consent.method', m.id as any)}
                           className={cn(
                             "w-full text-left p-4 rounded-2xl border-2 font-bold transition-all flex items-center justify-between",
                             watch('consent.method') === m.id ? "border-blue-600 bg-blue-50/50 dark:bg-blue-900/10 text-blue-700 dark:text-blue-400" : "border-slate-100 dark:border-slate-800 text-slate-500"
                           )}
                         >
                           {m.label}
                           {watch('consent.method') === m.id && <CheckCircle2 className="w-5 h-5" />}
                         </button>
                       ))}
                     </div>
                  </div>

                  <label className="flex items-start gap-3 p-4 bg-slate-50 dark:bg-slate-800 rounded-2xl cursor-pointer group hover:bg-slate-100 transition-colors">
                     <div className="relative mt-1">
                       <input
                         type="checkbox"
                         className="peer h-6 w-6 rounded-lg border-2 border-slate-300 dark:border-slate-700 appearance-none checked:bg-blue-600 checked:border-blue-600 transition-all"
                         {...register('consent.confirmed')}
                       />
                       <CheckCircle2 className="absolute top-0 left-0 w-6 h-6 text-white scale-0 peer-checked:scale-75 transition-transform" />
                     </div>
                     <p className="text-xs font-bold text-slate-600 dark:text-slate-400 leading-relaxed">
                       Household consents to data collection for needs assessment. Data protected under DPDP Act 2023. Household may opt out anytime.
                     </p>
                  </label>
                  {errors.consent?.confirmed && <p className="text-red-500 text-xs font-bold">{errors.consent.confirmed.message}</p>}
                </div>
              </div>

              <div className="flex gap-4">
                <button
                  type="button"
                  onClick={prevStep}
                  className="flex-1 bg-white dark:bg-slate-900 text-slate-900 dark:text-white font-black py-5 rounded-3xl border-2 border-slate-100 dark:border-slate-800 active:scale-95 transition-transform"
                >
                  Back
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-[2] bg-emerald-500 hover:bg-emerald-600 text-white font-black py-5 rounded-3xl shadow-xl shadow-emerald-500/30 flex items-center justify-center gap-2 active:scale-95 transition-transform disabled:opacity-50"
                >
                  {loading ? 'Registering...' : 'Register Household'}
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </form>
    </div>
  );
};

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  UserPlus, MapPin, Phone, MessageSquare, ChevronRight,
  Globe, Briefcase, Clock, Shield, CheckCircle, ArrowRight, ArrowLeft,
  Loader2, Star, X
} from 'lucide-react';
import { toast } from 'react-hot-toast';
import { VolunteerAPI, TenantAPI } from '../api/endpoints';
import { cn } from '../lib/utils';
import { useAuthStore } from '../stores/auth.store';
import { useTenantStore } from '../stores/tenant.store';
import { TenantSelector } from '../components/TenantSelector';

type Step = 1 | 2 | 3;

const SKILL_OPTIONS = [
  { id: 'first_aid', label: 'First Aid', icon: '🩹' },
  { id: 'medical', label: 'Medical', icon: '⚕️' },
  { id: 'counseling', label: 'Counseling', icon: '🧠' },
  { id: 'logistics', label: 'Logistics', icon: '📦' },
  { id: 'translation', label: 'Translation', icon: '🌐' },
  { id: 'driving', label: 'Driving', icon: '🚗' },
  { id: 'cooking', label: 'Cooking', icon: '🍳' },
  { id: 'construction', label: 'Construction', icon: '🔨' },
  { id: 'childcare', label: 'Childcare', icon: '👶' },
  { id: 'teaching', label: 'Teaching', icon: '📚' },
  { id: 'search_rescue', label: 'Search & Rescue', icon: '🔍' },
  { id: 'water_sanitation', label: 'WaSH', icon: '💧' },
];

const LANGUAGE_OPTIONS = [
  'English', 'Hindi', 'Marathi', 'Tamil', 'Bengali', 'Urdu', 'Gujarati', 'Kannada', 'Telugu', 'Malayalam'
];

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const TIME_SLOTS = ['morning', 'afternoon', 'evening'];

export function VolunteerRegistrationPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>(1);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Step 1: Basic Info
  const [skills, setSkills] = useState<string[]>([]);
  const [skillDetails, setSkillDetails] = useState<Record<string, { proficiency: string; evidence?: string }>>({});
  const [languages, setLanguages] = useState<string[]>(['English']);
  const [maxDistance, setMaxDistance] = useState(10);
  const [wardId, setWardId] = useState('');

  // Step 2: Contact & Location
  const [whatsappNumber, setWhatsappNumber] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [preferredChannel, setPreferredChannel] = useState('push');
  const [latitude, setLatitude] = useState<number | null>(null);
  const [longitude, setLongitude] = useState<number | null>(null);

  // Step 3: Availability
  const [availability, setAvailability] = useState<Record<string, string[]>>({});
  const [culturalTags, setCulturalTags] = useState<string[]>([]);
  const [customTag, setCustomTag] = useState('');

  // Platform Admin specific
  const { role } = useAuthStore();
  const [selectedTenantId, setSelectedTenantId] = useState<string>('');

  const toggleSkill = (id: string) => {
    if (skills.includes(id)) {
      setSkills(prev => prev.filter(s => s !== id));
      const newDetails = { ...skillDetails };
      delete newDetails[id];
      setSkillDetails(newDetails);
    } else {
      setSkills(prev => [...prev, id]);
      setSkillDetails(prev => ({ ...prev, [id]: { proficiency: 'intermediate' } }));
    }
  };

  const updateSkillDetail = (id: string, field: 'proficiency' | 'evidence', value: string) => {
    setSkillDetails(prev => ({
      ...prev,
      [id]: { ...prev[id], [field]: value }
    }));
  };

  const toggleLanguage = (lang: string) =>
    setLanguages(prev => prev.includes(lang) ? prev.filter(l => l !== lang) : [...prev, lang]);

  const toggleAvailability = (day: string, slot: string) => {
    setAvailability(prev => {
      const current = prev[day] || [];
      const updated = current.includes(slot) ? current.filter(s => s !== slot) : [...current, slot];
      return { ...prev, [day]: updated };
    });
  };

  const addCulturalTag = () => {
    if (customTag.trim() && !culturalTags.includes(customTag.trim())) {
      setCulturalTags(prev => [...prev, customTag.trim()]);
      setCustomTag('');
    }
  };

  const captureLocation = () => {
    if (!navigator.geolocation) {
      toast.error('Geolocation not supported');
      return;
    }
    toast.loading('Capturing GPS...', { id: 'gps' });
    navigator.geolocation.getCurrentPosition(
      pos => {
        setLatitude(pos.coords.latitude);
        setLongitude(pos.coords.longitude);
        toast.success('Location captured!', { id: 'gps' });
      },
      () => toast.error('Could not get location', { id: 'gps' }),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  const handleSubmit = async () => {
    if (skills.length === 0) {
      toast.error('Select at least one skill');
      return;
    }

    setIsSubmitting(true);
    try {
      const payload = {
        skills,
        preferred_language: languages,
        skill_proficiency: Object.keys(skillDetails).reduce((acc, k) => ({
          ...acc,
          [k]: skillDetails[k].proficiency
        }), {}),
        skill_verification: Object.keys(skillDetails).reduce((acc, k) => ({
          ...acc,
          [k]: { evidence: skillDetails[k].evidence, status: 'pending' }
        }), {}),
        cultural_context_tags: culturalTags,
        max_distance_km: maxDistance,
        availability_schedule: availability,
        ward_id: wardId || undefined,
        whatsapp_number: whatsappNumber || undefined,
        phone_number: phoneNumber || undefined,
        preferred_channel: preferredChannel,
        latitude: latitude || undefined,
        longitude: longitude || undefined,
        tenant_id: role === 'platform_admin' ? selectedTenantId : undefined,
      };

      const res = await VolunteerAPI.create(payload);
      toast.success(`Volunteer ${res.data.volunteer_id.slice(0, 8)} registered!`, {
        duration: 4000,
        icon: '🎉',
        style: { background: '#2E7D32', color: '#fff', fontWeight: 'bold' }
      });
      navigate('/volunteers');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Registration failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-brand-50/30 py-10 px-6">
      <div className="max-w-3xl mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-brand-600 rounded-2xl flex items-center justify-center text-white shadow-lg shadow-brand-200">
              <UserPlus className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-brand-900 tracking-tight">Volunteer Registration</h1>
              <p className="text-sm text-slate-500">Join the NEXUS field response network</p>
            </div>
          </div>
          <button onClick={() => navigate('/volunteers')} className="p-2 hover:bg-gray-100 rounded-full transition-colors">
            <X className="w-6 h-6 text-gray-400" />
          </button>
        </div>

        {/* Stepper */}
        <div className="mb-12 relative">
          <div className="absolute top-1/2 left-0 w-full h-[2px] bg-gray-200 -z-10 -translate-y-1/2" />
          <div
            className="absolute top-1/2 left-0 h-[2px] bg-brand-600 -z-10 -translate-y-1/2 transition-all duration-500"
            style={{ width: `${((step - 1) / 2) * 100}%` }}
          />
          <div className="flex justify-between">
            {[
              { id: 1, label: 'Skills & Profile', icon: Briefcase },
              { id: 2, label: 'Contact & Location', icon: MapPin },
              { id: 3, label: 'Availability', icon: Clock },
            ].map(s => (
              <div key={s.id} className="flex flex-col items-center gap-2">
                <button
                  onClick={() => s.id < step && setStep(s.id as Step)}
                  disabled={s.id > step}
                  className={cn(
                    "w-12 h-12 rounded-full flex items-center justify-center ring-8 ring-white transition-all shadow-sm",
                    step === s.id ? 'bg-brand-600 text-white scale-110 shadow-lg shadow-brand-200' :
                    step > s.id ? 'bg-brand-100 text-brand-600' : 'bg-gray-200 text-gray-400'
                  )}
                >
                  <s.icon className="w-5 h-5" />
                </button>
                <span className={cn(
                  "text-[10px] font-bold uppercase tracking-wider",
                  step >= s.id ? 'text-brand-600' : 'text-gray-400'
                )}>{s.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Step 1: Skills & Profile */}
        {step === 1 && (
          <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} className="space-y-8">
            {role === 'platform_admin' && (
              <section className="bg-white p-8 rounded-3xl border border-warm-border shadow-sm space-y-6">
                <h2 className="text-xl font-bold text-brand-900 flex items-center gap-2">
                  <Shield className="w-5 h-5 text-brand-600" /> Admin: Select Organization
                </h2>
                <p className="text-sm text-slate-500">Since you are a Platform Admin, you must specify which organization this volunteer belongs to.</p>
                <TenantSelector
                  value={selectedTenantId}
                  onChange={setSelectedTenantId}
                  placeholder="Select NGO..."
                />
              </section>
            )}

            <section className="bg-white p-8 rounded-3xl border border-warm-border shadow-sm space-y-6">
              <h2 className="text-xl font-bold text-brand-900 flex items-center gap-2">
                <Star className="w-5 h-5 text-brand-600" /> Skills & Capabilities
              </h2>
              <p className="text-sm text-gray-500">Select all skills you can deploy in the field.</p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  {SKILL_OPTIONS.map(skill => (
                    <div key={skill.id} className="space-y-2">
                      <button
                        onClick={() => toggleSkill(skill.id)}
                        className={cn(
                          "w-full p-4 rounded-2xl flex flex-col items-center gap-2 transition-all border",
                          skills.includes(skill.id)
                            ? 'bg-brand-600 text-white border-brand-600 shadow-lg'
                            : 'bg-gray-50 text-gray-600 border-gray-100 hover:bg-gray-100'
                        )}
                      >
                        <span className="text-2xl">{skill.icon}</span>
                        <span className="text-[10px] font-bold uppercase tracking-tight text-center">{skill.label}</span>
                      </button>
                      
                      {skills.includes(skill.id) && (
                        <div className="bg-slate-50 p-3 rounded-xl border border-slate-200 space-y-3 animate-in fade-in slide-in-from-top-2">
                          <div>
                            <label className="text-[9px] font-bold text-slate-400 uppercase block mb-1">Proficiency</label>
                            <select 
                              value={skillDetails[skill.id]?.proficiency}
                              onChange={(e) => updateSkillDetail(skill.id, 'proficiency', e.target.value)}
                              className="w-full text-[10px] bg-white border border-slate-200 rounded p-1"
                            >
                              <option value="beginner">Beginner</option>
                              <option value="intermediate">Intermediate</option>
                              <option value="expert">Expert / Trainer</option>
                            </select>
                          </div>
                          {(['medical', 'search_rescue', 'driving', 'first_aid'].includes(skill.id)) && (
                            <div>
                              <label className="text-[9px] font-bold text-slate-400 uppercase block mb-1">License / Cert ID</label>
                              <input 
                                type="text"
                                placeholder="ID or URL..."
                                value={skillDetails[skill.id]?.evidence || ''}
                                onChange={(e) => updateSkillDetail(skill.id, 'evidence', e.target.value)}
                                className="w-full text-[10px] bg-white border border-slate-200 rounded p-1"
                              />
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
            </section>

            <section className="bg-white p-8 rounded-3xl border border-warm-border shadow-sm space-y-6">
              <h2 className="text-xl font-bold text-brand-900 flex items-center gap-2">
                <Globe className="w-5 h-5 text-brand-600" /> Languages Spoken
              </h2>
              <div className="flex flex-wrap gap-2">
                {LANGUAGE_OPTIONS.map(lang => (
                  <button
                    key={lang}
                    onClick={() => toggleLanguage(lang)}
                    className={cn(
                      "px-4 py-2 rounded-full text-sm font-bold transition-all border",
                      languages.includes(lang)
                        ? 'bg-brand-600 text-white border-brand-600'
                        : 'bg-white text-gray-600 border-gray-200 hover:border-brand-300'
                    )}
                  >
                    {lang}
                  </button>
                ))}
              </div>
            </section>

            <section className="bg-white p-8 rounded-3xl border border-warm-border shadow-sm space-y-6">
              <h2 className="text-xl font-bold text-brand-900">Deployment Range</h2>
              <div>
                <div className="flex justify-between items-center mb-3">
                  <span className="text-sm text-gray-600">Maximum travel distance</span>
                  <span className="font-mono font-bold text-brand-600 text-lg">{maxDistance} km</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={50}
                  value={maxDistance}
                  onChange={e => setMaxDistance(Number(e.target.value))}
                  className="w-full accent-brand-600"
                />
                <div className="flex justify-between text-[10px] text-gray-400 font-mono mt-1">
                  <span>1 km</span>
                  <span>50 km</span>
                </div>
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2">Assigned Ward (Optional)</label>
                <input
                  type="text"
                  value={wardId}
                  onChange={e => setWardId(e.target.value)}
                  placeholder="e.g., ward-4"
                  className="w-full px-5 py-3 bg-slate-50 border border-warm-border rounded-xl text-sm focus:outline-none focus:border-brand-600"
                />
              </div>
            </section>
          </motion.div>
        )}

        {/* Step 2: Contact & Location */}
        {step === 2 && (
          <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="space-y-8">
            <section className="bg-white p-8 rounded-3xl border border-warm-border shadow-sm space-y-6">
              <h2 className="text-xl font-bold text-brand-900 flex items-center gap-2">
                <Phone className="w-5 h-5 text-brand-600" /> Contact Information
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2">WhatsApp Number</label>
                  <div className="relative">
                    <MessageSquare className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-green-500" />
                    <input
                      type="tel"
                      value={whatsappNumber}
                      onChange={e => setWhatsappNumber(e.target.value)}
                      placeholder="+91 9876543210"
                      className="w-full pl-11 pr-4 py-3 bg-slate-50 border border-warm-border rounded-xl text-sm focus:outline-none focus:border-brand-600"
                    />
                  </div>
                </div>
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2">Phone Number</label>
                  <div className="relative">
                    <Phone className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                      type="tel"
                      value={phoneNumber}
                      onChange={e => setPhoneNumber(e.target.value)}
                      placeholder="+91 9876543210"
                      className="w-full pl-11 pr-4 py-3 bg-slate-50 border border-warm-border rounded-xl text-sm focus:outline-none focus:border-brand-600"
                    />
                  </div>
                </div>
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2">Preferred Notification Channel</label>
                <div className="flex bg-slate-50 p-1.5 rounded-2xl border border-warm-border gap-1">
                  {[
                    { id: 'push', label: 'Push' },
                    { id: 'whatsapp', label: 'WhatsApp' },
                    { id: 'sms', label: 'SMS' },
                  ].map(ch => (
                    <button
                      key={ch.id}
                      onClick={() => setPreferredChannel(ch.id)}
                      className={cn(
                        "flex-1 py-2.5 rounded-xl text-xs font-bold transition-all",
                        preferredChannel === ch.id
                          ? 'bg-white text-brand-600 shadow-sm'
                          : 'text-gray-400 hover:text-gray-600'
                      )}
                    >
                      {ch.label}
                    </button>
                  ))}
                </div>
              </div>
            </section>

            <section className="bg-white p-8 rounded-3xl border border-warm-border shadow-sm space-y-6">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-bold text-brand-900 flex items-center gap-2">
                  <MapPin className="w-5 h-5 text-brand-600" /> Home Location
                </h2>
                <button
                  onClick={captureLocation}
                  className="flex items-center gap-2 px-4 py-2 bg-brand-50 text-brand-600 font-bold text-sm rounded-xl hover:bg-brand-100 transition-colors"
                >
                  <MapPin className="w-4 h-4" /> Capture GPS
                </button>
              </div>
              {latitude && longitude ? (
                <div className="bg-green-50 border border-green-200 p-4 rounded-2xl flex items-center gap-3">
                  <CheckCircle className="w-5 h-5 text-green-600" />
                  <div>
                    <p className="text-sm font-bold text-green-800">Location Captured</p>
                    <p className="text-xs text-green-600 font-mono">{latitude.toFixed(6)}, {longitude.toFixed(6)}</p>
                  </div>
                </div>
              ) : (
                <div className="bg-slate-50 border border-dashed border-gray-300 p-8 rounded-2xl text-center">
                  <MapPin className="w-8 h-8 text-gray-300 mx-auto mb-2" />
                  <p className="text-sm text-gray-400">Click "Capture GPS" to set your home coordinates</p>
                  <p className="text-[10px] text-gray-300 mt-1">Used for proximity-based task matching</p>
                </div>
              )}
            </section>
          </motion.div>
        )}

        {/* Step 3: Availability */}
        {step === 3 && (
          <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="space-y-8">
            <section className="bg-white p-8 rounded-3xl border border-warm-border shadow-sm space-y-6">
              <h2 className="text-xl font-bold text-brand-900 flex items-center gap-2">
                <Clock className="w-5 h-5 text-brand-600" /> Weekly Availability
              </h2>
              <p className="text-sm text-gray-500">Tap cells to mark when you're available for deployment.</p>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr>
                      <th className="text-left text-[10px] font-bold text-gray-400 uppercase tracking-widest pb-3 pr-4">Day</th>
                      {TIME_SLOTS.map(slot => (
                        <th key={slot} className="text-center text-[10px] font-bold text-gray-400 uppercase tracking-widest pb-3 px-2">{slot}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {DAYS.map(day => (
                      <tr key={day} className="border-t border-gray-50">
                        <td className="py-2 pr-4 text-sm font-semibold text-brand-900 capitalize">{day}</td>
                        {TIME_SLOTS.map(slot => {
                          const isActive = (availability[day] || []).includes(slot);
                          return (
                            <td key={slot} className="py-2 px-2 text-center">
                              <button
                                onClick={() => toggleAvailability(day, slot)}
                                className={cn(
                                  "w-full py-3 rounded-xl text-xs font-bold transition-all border",
                                  isActive
                                    ? 'bg-brand-600 text-white border-brand-600 shadow-sm'
                                    : 'bg-gray-50 text-gray-300 border-gray-100 hover:bg-gray-100 hover:text-gray-500'
                                )}
                              >
                                {isActive ? '✓' : '–'}
                              </button>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="bg-white p-8 rounded-3xl border border-warm-border shadow-sm space-y-6">
              <h2 className="text-xl font-bold text-brand-900 flex items-center gap-2">
                <Shield className="w-5 h-5 text-brand-600" /> Cultural Context Tags
              </h2>
              <p className="text-sm text-gray-500">Optional tags to help match you with culturally appropriate deployments.</p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={customTag}
                  onChange={e => setCustomTag(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addCulturalTag())}
                  placeholder="e.g., speaks-local-dialect, women-friendly..."
                  className="flex-1 px-4 py-2.5 bg-slate-50 border border-warm-border rounded-xl text-sm focus:outline-none focus:border-brand-600"
                />
                <button
                  onClick={addCulturalTag}
                  className="px-5 py-2.5 bg-brand-600 text-white rounded-xl text-sm font-bold hover:bg-brand-800 transition-colors"
                >
                  Add
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {culturalTags.map(tag => (
                  <span key={tag} className="px-3 py-1.5 bg-brand-50 text-brand-700 rounded-lg text-xs font-bold flex items-center gap-2 border border-brand-100">
                    {tag}
                    <button onClick={() => setCulturalTags(prev => prev.filter(t => t !== tag))} className="text-brand-400 hover:text-red-500">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
                {culturalTags.length === 0 && (
                  <span className="text-xs text-gray-400 italic">No tags added yet</span>
                )}
              </div>
            </section>

            {/* Review Summary */}
            <section className="bg-brand-900 text-white p-8 rounded-3xl shadow-2xl shadow-brand-900/20 space-y-4">
              <h3 className="text-xs font-bold uppercase tracking-widest text-brand-300">Registration Summary</h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-brand-400 text-xs">Skills</span>
                  <p className="font-bold">{skills.length} selected</p>
                </div>
                <div>
                  <span className="text-brand-400 text-xs">Languages</span>
                  <p className="font-bold">{languages.join(', ')}</p>
                </div>
                <div>
                  <span className="text-brand-400 text-xs">Max Range</span>
                  <p className="font-bold font-mono">{maxDistance} km</p>
                </div>
                <div>
                  <span className="text-brand-400 text-xs">Channel</span>
                  <p className="font-bold capitalize">{preferredChannel}</p>
                </div>
              </div>
            </section>
          </motion.div>
        )}

        {/* Footer Navigation */}
        <div className="flex justify-between items-center pt-8 mt-8 border-t border-gray-100">
          <button
            onClick={() => step > 1 ? setStep((step - 1) as Step) : navigate('/volunteers')}
            className="flex items-center gap-2 px-6 py-3 rounded-xl text-gray-500 font-bold text-sm hover:bg-gray-100 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            {step === 1 ? 'Cancel' : 'Back'}
          </button>

          {step < 3 ? (
            <button
              onClick={() => setStep((step + 1) as Step)}
              className="flex items-center gap-2 px-8 py-3 rounded-xl bg-brand-600 text-white font-bold text-sm hover:bg-brand-800 transition-all shadow-lg shadow-brand-100"
            >
              Continue
              <ArrowRight className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={isSubmitting || skills.length === 0}
              className="flex items-center gap-2 px-10 py-3.5 rounded-xl bg-green-600 text-white font-bold text-sm hover:bg-green-700 transition-all shadow-lg shadow-green-100 disabled:opacity-50"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Registering...
                </>
              ) : (
                <>
                  <CheckCircle className="w-4 h-4" />
                  Complete Registration
                </>
              )}
            </button>
          )}
        </div>

      </div>
    </div>
  );
}

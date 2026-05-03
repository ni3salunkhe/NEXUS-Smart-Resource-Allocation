import React, { useState, useEffect, useRef } from 'react';
import { cn } from '../lib/utils';
import { 
  ChevronRight, 
  Search, 
  MapPin, 
  Plus, 
  Minus, 
  UserPlus, 
  Users,
  ArrowRight, 
  X,
  History,
  Calendar,
  Clock,
  CheckCircle,
  ShieldAlert,
  Shield,
  Building2,
  Loader2,
  Heart, 
  Utensils, 
  Home as HomeIcon, 
  Droplets, 
  GraduationCap, 
  Briefcase, 
  Sparkles, 
  Brain, 
  Truck, 
  Wifi, 
  Package,
  Mic
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { useSearchParams, useNavigate, useParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { useHouseholdStore } from '../stores/household.store';
import { useTenantStore } from '../stores/tenant.store';
import { useAuthStore } from '../stores/auth.store';
import { TenantSelector } from '../components/TenantSelector';
import { 
  prepareHouseholdPayload, 
  prepareNeedPayload, 
  prepareConsentPayload 
} from '../lib/intakeMappings';

type Step = 1 | 2 | 3 | 4;

interface MemberRow {
  id: string;
  role: string;
  age: 'infant' | 'child' | 'youth' | 'adult' | 'elderly' | '';
  gender: string;
  vulnerability: {
    disabled: boolean;
    chronic_illness: boolean;
    pregnant: boolean;
  };
}

const CATEGORIES = [
  { id: 'food', label: 'Food', icon: Utensils },
  { id: 'health', label: 'Health', icon: Heart },
  { id: 'shelter', label: 'Shelter', icon: HomeIcon },
  { id: 'water', label: 'Water', icon: Droplets },
  { id: 'education', label: 'Education', icon: GraduationCap },
  { id: 'protection', label: 'Protection', icon: Shield },
  { id: 'livelihood', label: 'Livelihood', icon: Briefcase },
  { id: 'hygiene', label: 'Hygiene', icon: Sparkles },
  { id: 'mental_health', label: 'Mental Health', icon: Brain },
  { id: 'logistics', label: 'Logistics', icon: Truck },
  { id: 'connect', label: 'Connect', icon: Wifi },
  { id: 'supplies', label: 'Supplies', icon: Package },
];

export function IntakeRegistrationPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEditMode = !!id;
  const { updateHousehold, addHousehold, getHousehold } = useHouseholdStore();
  const hhIdRef = useRef(`HH-${Math.floor(10000 + Math.random() * 90000)}`);

  const [searchParams, setSearchParams] = useSearchParams();
  const step = (parseInt(searchParams.get('step') || '1', 10) as Step);
  
  const { tenant_id: defaultTenantId, tenant_name: defaultTenantName, setTenant } = useTenantStore();
  const { role } = useAuthStore();
  const [selectedTenantId, setSelectedTenantId] = useState(defaultTenantId || '');
  const [selectedTenantName, setSelectedTenantName] = useState(defaultTenantName || '');
  const draftId = searchParams.get('draftId');

  // When platform_admin picks a tenant, propagate to store so API interceptor sends X-Tenant-ID
  const handleTenantChange = (tenant: { tenant_id: string; name: string; slug: string }) => {
    setSelectedTenantId(tenant.tenant_id);
    setSelectedTenantName(tenant.name);
    if (tenant.tenant_id) {
      setTenant(tenant.tenant_id, tenant.name, tenant.slug);
    }
  };

  const setStep = (newStep: Step) => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set('step', newStep.toString());
    setSearchParams(newParams);
    // Automatic scroll to top on step change as requested in previous diagnosis
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSaveIdentity = () => {
    const hhData: any = {
      draftId: draftId || `draft-${Date.now()}`,
      tenant_id: selectedTenantId || defaultTenantId,
      display_name: members[0]?.name || 'Unnamed Household',
      step,
      total_members: totalMembers,
      location_description: locationDesc,
      dwelling_type: dwellingType,
      economic_tier: economicTier,
      ward_id: wardId,
      location: { latitude: lat, longitude: lng },
      members,
      selectedCategory,
      needDescription,
      permissionScopes,
      lastSaved: new Date().toISOString()
    };

    try {
      const existingDrafts = JSON.parse(localStorage.getItem('nexus_drafts') || '[]');
      const updatedDrafts = existingDrafts.filter((d: any) => d.draftId !== hhData.draftId);
      updatedDrafts.push(hhData);
      localStorage.setItem('nexus_drafts', JSON.stringify(updatedDrafts));
      toast.info('Draft saved successfully! You can resume it from the Households page.');
      navigate('/households');
    } catch (e) {
      toast.error('Failed to save draft locally.');
    }
  };

  const handleCaptureGPS = () => {
    if (!navigator.geolocation) {
      toast.error('Geolocation is not supported by your browser');
      return;
    }

    const toastId = toast.loading('Capturing precise coordinates...');
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLat(position.coords.latitude);
        setLng(position.coords.longitude);
        toast.update(toastId, { render: 'Location captured successfully', type: 'success', isLoading: false, autoClose: 3000 });
      },
      (error) => {
        toast.update(toastId, { render: 'Could not capture location. Please enter manually.', type: 'error', isLoading: false, autoClose: 3000 });
        console.error(error);
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  };

  const handleSubmit = async () => {
    if (isSubmitting) return;
    
    // Guard: platform_admin MUST select an org before submitting
    const effectiveTenantId = useTenantStore.getState().tenant_id;
    if (!effectiveTenantId && role === 'platform_admin') {
      toast.error('Please select an organization before submitting.');
      return;
    }

    setIsSubmitting(true);
    const toastId = toast.loading('Submitting intake report...');

    const hhPayload = prepareHouseholdPayload({
      ward_id: wardId,
      display_name: members[0]?.name || 'Unnamed Household',
      location: { latitude: lat, longitude: lng },
      location_description: locationDesc,
      dwelling_type: dwellingType,
      economic_tier: economicTier,
      members,
    });

    let finalHouseholdId = id;

    try {
      if (isEditMode) {
        await updateHousehold(id!, hhPayload);
      } else {
        const { HouseholdAPI } = await import('../api/endpoints');
        const res = await HouseholdAPI.create(hhPayload);
        finalHouseholdId = res.data.household_id;
      }
      
      if (!finalHouseholdId) {
        throw new Error('Household was created but no ID was returned from server.');
      }

      // Step 2: Submit need
      const needPayload = prepareNeedPayload({
        selectedCategory,
        needDescription,
        location: { latitude: lat, longitude: lng },
        total_members: totalMembers,
        members,
      }, finalHouseholdId);

      if (needPayload) {
        const { NeedAPI } = await import('../api/endpoints');
        await NeedAPI.ingestMobile(needPayload);
      }

      // Step 3: Persist consent
      const consentPayload = prepareConsentPayload({ permissionScopes });
      if (finalHouseholdId && consentPayload) {
        const { HouseholdAPI } = await import('../api/endpoints');
        await HouseholdAPI.addConsent(finalHouseholdId, consentPayload);
      }

      // Clean up draft if one existed
      if (draftId) {
        const existingDrafts = JSON.parse(localStorage.getItem('nexus_drafts') || '[]');
        const updatedDrafts = existingDrafts.filter((d: any) => d.draftId !== draftId);
        localStorage.setItem('nexus_drafts', JSON.stringify(updatedDrafts));
      }

      toast.update(toastId, { render: 'Intake Report Submitted Successfully', type: 'success', isLoading: false, autoClose: 3000 });
      navigate('/households');
    } catch (err: any) {
      console.error('Submission failed:', err);
      const errorMsg = err.response?.data?.detail || err.message || 'Submission failed. Please try again.';
      toast.update(toastId, { 
        render: `Error: ${typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg)}`, 
        type: 'error', 
        isLoading: false, 
        autoClose: 8000 
      });
    } finally {
      setIsSubmitting(false);
    }
  };
  
  // Phase 1 State
  const [resolutionResult, setResolutionResult] = useState<any>(null);
  const [isResolving, setIsResolving] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [totalMembers, setTotalMembers] = useState(1);
  const [registrationDate, setRegistrationDate] = useState(new Date().toISOString().split('T')[0]);
  const [registrationTime, setRegistrationTime] = useState(new Date().toTimeString().split(' ')[0].slice(0, 5));
  const [locationDesc, setLocationDesc] = useState('');
  const [wardId, setWardId] = useState('');          // H2: ward_id
  const [lat, setLat] = useState(19.0330);
  const [lng, setLng] = useState(72.8634);
  const [dwellingType, setDwellingType] = useState('makeshift');
  const [economicTier, setEconomicTier] = useState('Tier 1 (Extreme Vulnerability)');
  const [members, setMembers] = useState<MemberRow[]>([
    {
      id: Math.random().toString(36).substr(2, 9),
      name: '',
      role: 'Head of Household',
      age: 'adult',   // H3: default to valid bracket value
      gender: 'female',
      vulnerability: { disabled: false, chronic_illness: false, pregnant: false },
    },
  ]);

  // Phase 2 State
  const [selectedCategory, setSelectedCategory] = useState('health');
  const [subcategory, setSubcategory] = useState('Primary Care / Medical Consultation');
  const [needDescription, setNeedDescription] = useState('');
  const [urgencyScore, setUrgencyScore] = useState(0.72);
  const [beneficiariesAffected, setBeneficiariesAffected] = useState(7);
  const [infoSource, setInfoSource] = useState('In Person');
  const [assessmentDate, setAssessmentDate] = useState(new Date().toISOString().split('T')[0]);
  const [localTime, setLocalTime] = useState(new Date().toTimeString().split(' ')[0].slice(0, 5));

  // Phase 3 State
  const [consentMethod, setConsentMethod] = useState('Verbal Affirmation');
  const [consentLanguage, setConsentLanguage] = useState('Arabic (Standard)');
  const [permissionScopes, setPermissionScopes] = useState<string[]>(['needs_assessment', 'resource_dispatch']);
  
  const PURPOSES = [
    { id: 'needs_assessment', label: 'Needs Assessment', desc: 'Identify and categorize your household requirements.', essential: true },
    { id: 'resource_dispatch', label: 'Resource Dispatch', desc: 'Allow volunteers to see your location for delivery.', essential: true },
    { id: 'impact_reporting', label: 'Impact Reporting', desc: 'Share anonymized data with funders for program evaluation.', essential: false },
    { id: 'cross_org_coordination', label: 'Cross-Org Linking', desc: 'Check if other NGOs are already providing you support.', essential: false },
    { id: 'anonymized_analytics', label: 'Analytics', desc: 'Contribute to regional heatmaps and trend analysis.', essential: false },
  ];

  const toggleScope = (id: string) => {
    setPermissionScopes(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]);
  };

  // Load data for edit mode from store or API
  useEffect(() => {
    const loadData = async () => {
      // 1. If we have a draftId, load from localStorage first
      if (draftId) {
        const drafts = JSON.parse(localStorage.getItem('nexus_drafts') || '[]');
        const draft = drafts.find((d: any) => d.draftId === draftId);
        if (draft) {
          setLocationDesc(draft.location_description || '');
          setLat(draft.location?.latitude || 19.0330);
          setLng(draft.location?.longitude || 72.8634);
          setTotalMembers(draft.total_members || 1);
          setDwellingType(draft.dwelling_type || 'makeshift');
          setEconomicTier(draft.economic_tier || 'Tier 1 (Extreme Vulnerability)');
          setWardId(draft.ward_id || '');
          if (draft.members && draft.members.length > 0) setMembers(draft.members);
          if (draft.selectedCategory) setSelectedCategory(draft.selectedCategory);
          if (draft.needDescription) setNeedDescription(draft.needDescription);
          if (draft.permissionScopes) setPermissionScopes(draft.permissionScopes);
          return; // Skip loading from backend
        }
      }

      if (!isEditMode) return;
      
      let existing = getHousehold(id);
      
      if (!existing) {
        setIsLoading(true);
        try {
          const { HouseholdAPI } = await import('../api/endpoints');
          const res = await HouseholdAPI.get(id!);
          existing = res.data;
          // Sync to local store if needed (optional, but good for consistency)
        } catch (err) {
          toast.error('Failed to load existing household data');
        } finally {
          setIsLoading(false);
        }
      }

      if (existing) {
        setLocationDesc(existing.location_description || '');
        setLat(existing.location?.latitude || existing.latitude || 19.0330);
        setLng(existing.location?.longitude || existing.longitude || 72.8634);
        setTotalMembers(existing.total_members || 1);
        setDwellingType(existing.dwelling_type || 'makeshift');
        setEconomicTier(existing.economic_tier || 'Tier 1 (Extreme Vulnerability)');
        
        if (existing.members && existing.members.length > 0) {
          setMembers(existing.members.map((m: any) => ({
            id: m.member_id || Math.random().toString(36).substr(2, 9),
            role: m.role_in_household || 'Other',
            age: m.age_bracket || '',
            gender: m.gender || 'Other',
            vulnerability: m.vulnerability_flags || { disabled: false, chronic_illness: false, pregnant: false }
          })));
        }
      }
    };
    
    loadData();
  }, [id, isEditMode, getHousehold, draftId]);

  // Synchronize members list with totalMembers count
  useEffect(() => {
    if (members.length < totalMembers) {
      const needed = totalMembers - members.length;
      const newMembers = Array.from({ length: needed }).map((_, i) => ({
        id: Math.random().toString(36).substr(2, 9),
        role: i === 0 && members.length === 0 ? 'Head of Household' : 'Member',
        age: '',
        gender: 'female',
        vulnerability: { disabled: false, chronic_illness: false, pregnant: false }
      }));
      setMembers([...members, ...newMembers]);
    } else if (members.length > totalMembers) {
      setMembers(members.slice(0, totalMembers));
    }
  }, [totalMembers, members.length]);

  const updateMember = (id: string, updates: Partial<MemberRow>) => {
    setMembers(prev => prev.map(m => m.id === id ? { ...m, ...updates } : m));
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-warm-50 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-brand-600/20 border-t-brand-600 rounded-full animate-spin" />
          <p className="text-sm font-bold text-brand-900 uppercase tracking-widest animate-pulse">Retrieving Household Case...</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`mx-auto px-6 py-8 pb-24 min-h-screen transition-all duration-500 ${step === 4 ? 'max-w-7xl' : 'max-w-3xl'}`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-brand-600 rounded-xl flex items-center justify-center text-white">
            <UserPlus className="w-6 h-6" />
          </div>
          <h1 className="font-headline text-3xl font-bold text-brand-900 italic">Clinical Sanctuary</h1>
        </div>
        <button 
          onClick={() => navigate('/households')}
          className="p-2 hover:bg-gray-100 rounded-full transition-colors"
        >
          <X className="w-6 h-6 text-gray-500" />
        </button>
      </div>

      {/* Breadcrumb */}
      <nav className="flex items-center text-sm text-gray-500 mb-8">
        <span 
          onClick={() => navigate('/')}
          className="hover:text-brand-600 cursor-pointer"
        >
          Panel
        </span>
        <ChevronRight className="w-4 h-4 mx-2 opacity-50" />
        <span 
          onClick={() => navigate('/households')}
          className="hover:text-brand-600 cursor-pointer"
        >
          Households
        </span>
        <ChevronRight className="w-4 h-4 mx-2 opacity-50" />
        <span className="text-brand-600 font-medium font-headline italic">Intake Registration</span>
      </nav>

      <div className="mb-10">
        <h2 className="font-headline text-4xl text-brand-900 mb-2">Intake Registration</h2>
        <p className="text-gray-600">Record new household details or locate an existing record to prioritize immediate needs.</p>
      </div>

      {/* Stepper */}
      <div className="mb-16 relative">
        <div className="absolute top-1/2 left-0 w-full h-[2px] bg-gray-200 -z-10 -translate-y-1/2" />
        <div 
          className="absolute top-1/2 left-0 h-[2px] bg-brand-600 -z-10 -translate-y-1/2 transition-all duration-500" 
          style={{ width: `${((step - 1) / 3) * 100}%` }}
        />
        
        <div className="flex justify-between">
          {[
            { id: 1, label: 'Identity' },
            { id: 2, label: 'Needs' },
            { id: 3, label: 'Consent' },
            { id: 4, label: 'Review' }
          ].map((s) => (
            <div key={s.id} className="flex flex-col items-center gap-2">
              <button 
                onClick={() => s.id < step && setStep(s.id as Step)}
                disabled={s.id > step}
                className={`w-10 h-10 rounded-full flex items-center justify-center font-mono text-sm font-bold ring-8 ring-background transition-all ${
                  step === s.id ? 'bg-brand-600 text-white scale-110' : 
                  step > s.id ? 'bg-brand-100 text-brand-600' : 'bg-gray-200 text-gray-500'
                }`}
              >
                {s.id}
              </button>
              <span className={`text-[10px] font-bold uppercase tracking-wider ${
                step >= s.id ? 'text-brand-600' : 'text-gray-400'
              }`}>{s.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Form Content */}
      <div className="space-y-8">
        <section className={cn(
            "p-8 rounded-3xl border-2 transition-all shadow-lg space-y-4",
            selectedTenantId ? "bg-white border-brand-200" : "bg-red-50/30 border-red-200"
          )}>
            <h3 className="font-headline text-xl text-brand-900 font-bold flex items-center gap-2">
              <Shield className="w-5 h-5 text-brand-600" />
              Organization Context Required
            </h3>
            <p className="text-sm text-slate-500">You must select an organization to file this record under.</p>
            <div className="flex items-center gap-3">
              <TenantSelector
                value={selectedTenantId}
                onChange={handleTenantChange}
                placeholder="Select Organization..."
                onAddOption={() => {
                  const name = prompt("Enter new organization name:");
                  if (name) {
                    const slug = name.toLowerCase().replace(/\s+/g, '-');
                    const newTenant = {
                      tenant_id: crypto.randomUUID(),
                      name: name,
                      slug: slug
                    };
                    handleTenantChange(newTenant);
                  }
                }}
              />
              {selectedTenantId && (
                <button 
                  onClick={() => {
                    setSelectedTenantId('');
                    setSelectedTenantName('');
                  }}
                  className="p-3 text-brand-600 hover:bg-brand-50 rounded-xl transition-all"
                  title="Clear Selection"
                >
                  <Plus className="w-5 h-5 rotate-45" />
                </button>
              )}
            </div>
            {!selectedTenantId && (
              <p className="text-xs text-red-600 font-bold flex items-center gap-1 animate-pulse mt-2">
                <ShieldAlert className="w-4 h-4" /> Please select an organization to enable Save/Submit.
              </p>
            )}
        </section>
        {step === 1 && (
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="space-y-8"
          >
            {/* Registration Metadata */}
        <section className="bg-white p-8 rounded-3xl border border-warm-border shadow-sm space-y-6">
          <h3 className="font-headline text-xl text-brand-900 font-bold border-b border-gray-100 pb-4 flex items-center gap-2">
            <History className="w-5 h-5 text-brand-600" />
            Registration Context
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2 flex items-center gap-2">
                <Calendar className="w-4 h-4 text-gray-400" />
                Intake Date
              </label>
              <input 
                type="date"
                value={registrationDate}
                onChange={(e) => setRegistrationDate(e.target.value)}
                className="w-full bg-gray-50 border-none rounded-xl p-3 text-sm focus:ring-2 focus:ring-brand-400/20"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2 flex items-center gap-2">
                <Clock className="w-4 h-4 text-gray-400" />
                Intake Time
              </label>
              <input 
                type="time"
                value={registrationTime}
                onChange={(e) => setRegistrationTime(e.target.value)}
                className="w-full bg-gray-50 border-none rounded-xl p-3 text-sm focus:ring-2 focus:ring-brand-400/20"
              />
            </div>
          </div>
        </section>

        {/* Locate Record */}
        <section className="bg-white p-8 rounded-3xl border border-warm-border shadow-sm">
          <h2 className="font-headline text-2xl text-brand-900 mb-6">Locate Record (Resolve)</h2>
          <div className="relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400" />
            <input 
              type="text" 
              placeholder="Search by phone, household ID, landmark, or ward..."
              className={cn(
                "w-full h-14 pl-12 pr-4 bg-gray-50 rounded-xl border-none focus:ring-2 transition-shadow",
                isResolving ? "opacity-50 pointer-events-none" : "focus:ring-brand-400/20"
              )}
              onBlur={async (e) => {
                if (e.target.value.length > 3) {
                  setIsResolving(true);
                  try {
                    const { IdentityAPI } = await import('../api/endpoints');
                    const res = await IdentityAPI.resolve({ 
                      description_text: e.target.value, 
                      tenant_id: selectedTenantId || 'default' 
                    });
                    setResolutionResult(res.data);
                    if (res.data.status === 'auto_linked' && res.data.household_id) {
                      toast.success(`System: Auto-linked to Household ${res.data.household_id.slice(0, 8)}`, { icon: '🤖' });
                      navigate(`/households/intake/${res.data.household_id}?step=2`);
                    } else if (res.data.status === 'review_required') {
                      toast.info('Multiple matches found. Please review candidates.');
                    }
                  } catch (err) {
                    toast.error('Identity resolution failed');
                  } finally {
                    setIsResolving(false);
                  }
                }
              }}
            />
            {isResolving && (
              <div className="absolute right-4 top-1/2 -translate-y-1/2">
                <div className="w-5 h-5 border-2 border-brand-600/30 border-t-brand-600 rounded-full animate-spin" />
              </div>
            )}
          </div>

          {resolutionResult && (
            <motion.div 
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              className="mt-8 space-y-4"
            >
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400">Resolution Engine Output</h3>
                <span className={cn(
                  "px-3 py-1 rounded-full text-[10px] font-bold uppercase",
                  resolutionResult.status === 'new_household' ? "bg-blue-50 text-blue-600" :
                  resolutionResult.status === 'review_required' ? "bg-amber-50 text-amber-600" : "bg-green-50 text-green-600"
                )}>
                  {resolutionResult.status.replace('_', ' ')}
                </span>
              </div>

              {resolutionResult.candidates && resolutionResult.candidates.length > 0 && (
                <div className="space-y-3">
                  {resolutionResult.candidates.map((cand: any) => (
                    <div key={cand.household_id} className="p-4 bg-gray-50 rounded-2xl border border-gray-100 flex items-center justify-between group hover:border-brand-200 transition-colors">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-sm font-bold text-slate-900">Household {cand.household_id.slice(0, 8)}</span>
                          <span className="text-[10px] font-mono bg-white px-2 py-0.5 rounded border border-gray-100 text-gray-400">
                            Conf: {(cand.confidence * 100).toFixed(0)}%
                          </span>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {cand.distance_m !== undefined && (
                            <span className="text-[10px] text-gray-500 flex items-center gap-1">
                              <MapPin className="w-3 h-3" /> {Math.round(cand.distance_m)}m away
                            </span>
                          )}
                          {cand.match_signals?.landmark_score > 0.5 && (
                            <span className="text-[10px] text-green-600 font-medium">Landmark Match</span>
                          )}
                        </div>
                      </div>
                      <button 
                        onClick={() => navigate(`/households/intake/${cand.household_id}?step=2`)}
                        className="px-4 py-2 bg-white border border-gray-200 rounded-xl text-xs font-bold hover:bg-brand-600 hover:text-white hover:border-brand-600 transition-all shadow-sm"
                      >
                        Link Record
                      </button>
                    </div>
                  ))}
                </div>
              )}
              
              {resolutionResult.status === 'new_household' && (
                <div className="p-6 bg-brand-50/50 rounded-2xl border border-brand-100/50 text-center">
                  <p className="text-xs text-brand-700 font-medium italic">No existing records match this description. Proceeding with new registration.</p>
                </div>
              )}
            </motion.div>
          )}

          <div className="mt-6 flex items-center justify-between text-sm text-gray-500">
            <span>{resolutionResult?.status === 'new_household' ? "System recommends new registration." : "Identity Resolution Active"}</span>
            <span className="px-3 py-1 bg-gray-100 rounded-full font-mono text-[11px] font-bold">4_STAGE_CASCADE</span>
          </div>
        </section>

        {/* Household Registration */}
        <section className="bg-white p-8 rounded-3xl border border-warm-border shadow-sm space-y-10">
          <h2 className="font-headline text-2xl text-brand-900 border-b border-gray-100 pb-4">Household Registration</h2>
          
          {/* Location Context */}
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400">Location Context</h3>
              <button 
                onClick={handleCaptureGPS}
                className="flex items-center gap-2 text-brand-600 font-bold text-sm hover:text-brand-800 transition-colors"
              >
                <MapPin className="w-4 h-4" />
                Capture GPS
              </button>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Informal Location Description</label>
              <textarea 
                className="w-full bg-gray-50 border-none rounded-xl p-4 text-sm focus:ring-2 focus:ring-brand-400/20"
                rows={3}
                placeholder="e.g., Behind the blue mosque, third tent on the right..."
                value={locationDesc}
                onChange={(e) => setLocationDesc(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Ward / Zone ID</label>
              <input
                type="text"
                className="w-full bg-gray-50 border-none rounded-xl p-3 text-sm focus:ring-2 focus:ring-brand-400/20"
                placeholder="e.g., WARD-14, Zone-B"
                value={wardId}
                onChange={(e) => setWardId(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-3">Landmark Tags</label>
              <div className="flex flex-wrap gap-2">
                {['Water Point A', 'North Gate', 'Clinic Alpha'].map(tag => (
                  <button key={tag} className="px-4 py-2 rounded-full border border-gray-200 text-sm hover:bg-gray-50 transition-colors">
                    {tag}
                  </button>
                ))}
                <button className="px-4 py-2 rounded-full border border-dashed border-gray-300 text-gray-400 text-sm hover:bg-gray-50 flex items-center gap-1">
                  <Plus className="w-4 h-4" /> Custom Tag
                </button>
              </div>
            </div>
          </div>

          {/* Dwelling & Status */}
          <div className="space-y-6 pt-6 border-t border-gray-100">
            <h3 className="text-xs font-bold uppercase tracking-wider text-gray-400">Dwelling & Status</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              <div className="space-y-2">
                <label className="block text-sm font-medium text-gray-700 mb-2">Dwelling Type</label>
                {[
                  { value: 'temp', label: 'Temporary Tent' },
                  { value: 'makeshift', label: 'Makeshift Shelter' },
                  { value: 'perm', label: 'Permanent Structure' }
                ].map((type) => (
                  <label 
                    key={type.value}
                    className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer hover:bg-gray-50 transition-colors ${
                      dwellingType === type.value ? 'bg-brand-50 border-brand-400 ring-1 ring-brand-400' : 'border-gray-200'
                    }`}
                  >
                    <input 
                      type="radio" 
                      name="dwelling" 
                      value={type.value} 
                      checked={dwellingType === type.value}
                      onChange={(e) => setDwellingType(e.target.value)}
                      className="text-brand-600 focus:ring-brand-600" 
                    />
                    <span className={`text-sm ${dwellingType === type.value ? 'text-brand-900 font-bold' : 'text-gray-700'}`}>
                      {type.label}
                    </span>
                  </label>
                ))}
              </div>
              <div className="space-y-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">Total Members</label>
                  <div className="flex items-center gap-4 bg-gray-50 w-fit rounded-xl p-1">
                    <button 
                      type="button"
                      onClick={() => totalMembers > 1 && setTotalMembers(m => m - 1)}
                      className="w-10 h-10 flex items-center justify-center rounded-lg text-gray-500 hover:bg-white hover:shadow-sm transition-all"
                    >
                      <Minus className="w-4 h-4" />
                    </button>
                    <span className="font-mono text-xl w-8 text-center font-bold text-brand-900">{totalMembers}</span>
                    <button 
                      type="button"
                      onClick={() => setTotalMembers(m => m + 1)}
                      className="w-10 h-10 flex items-center justify-center rounded-lg text-gray-500 hover:bg-white hover:shadow-sm transition-all"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">Economic Tier</label>
                  <select 
                    className="w-full bg-gray-50 border-none rounded-xl p-3 text-sm focus:ring-2 focus:ring-brand-400/20"
                    value={economicTier}
                    onChange={(e) => setEconomicTier(e.target.value)}
                  >
                    <option>Tier 1 (Extreme Vulnerability)</option>
                    <option>Tier 2 (Highly Vulnerable)</option>
                    <option>Tier 3 (Vulnerable)</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Member Details Disclosure */}
        <section className="bg-white rounded-3xl p-8 border border-gray-100 shadow-sm overflow-hidden">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-10 h-10 bg-brand-50 flex items-center justify-center rounded-xl text-brand-600">
              <Users className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-headline text-2xl font-medium text-brand-900 italic">Member Details</h3>
              <p className="text-xs text-gray-400 font-mono uppercase tracking-[0.2em] font-bold">Phase 1.C — Demographics</p>
            </div>
          </div>

          <div className="space-y-6">
            {members.map((member, index) => (
              <div 
                key={member.id}
                className="p-6 rounded-2xl border border-gray-100 bg-gray-50/50 hover:bg-white hover:border-brand-100 transition-all group"
              >
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center gap-3">
                    <span className="w-8 h-8 rounded-lg bg-brand-900 text-white flex items-center justify-center font-mono text-xs font-bold ring-4 ring-brand-50">
                      {index + 1}
                    </span>
                    <input 
                      type="text"
                      value={member.name}
                      placeholder="Full Name"
                      onChange={(e) => updateMember(member.id, { name: e.target.value })}
                      className="bg-transparent border-none font-headline text-lg font-bold text-brand-900 focus:ring-0 p-0 placeholder:text-gray-300 w-64"
                    />
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-gray-400 font-bold">ROLE:</span>
                      <input 
                        type="text"
                        value={member.role}
                        placeholder="Relationship to head"
                        onChange={(e) => updateMember(member.id, { role: e.target.value })}
                        className="bg-transparent border-none font-medium text-slate-500 focus:ring-0 p-0 text-sm placeholder:text-gray-300 w-40"
                      />
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                  <div>
                    <label className="block text-[10px] font-mono text-gray-400 uppercase tracking-widest font-bold mb-2">Age Bracket</label>
                    <select
                      value={member.age}
                      onChange={(e) => updateMember(member.id, { age: e.target.value as MemberRow['age'] })}
                      className="w-full bg-white border-gray-100 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-brand-400/20"
                    >
                      <option value="">Select...</option>
                      <option value="infant">Infant (0–5)</option>
                      <option value="child">Child (6–17)</option>
                      <option value="youth">Youth (18–24)</option>
                      <option value="adult">Adult (25–64)</option>
                      <option value="elderly">Elderly (65+)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-[10px] font-mono text-gray-400 uppercase tracking-widest font-bold mb-2">Gender</label>
                    <select 
                      value={member.gender}
                      onChange={(e) => updateMember(member.id, { gender: e.target.value })}
                      className="w-full bg-white border-gray-100 rounded-xl p-2.5 text-sm focus:ring-2 focus:ring-brand-400/20"
                    >
                      <option value="male">Male</option>
                      <option value="female">Female</option>
                      <option value="non_binary">Non-Binary</option>
                      <option value="prefer_not_to_say">Prefer not to say</option>
                    </select>
                  </div>
                  <div className="col-span-2">
                    <label className="block text-[10px] font-mono text-gray-400 uppercase tracking-widest font-bold mb-2">Vulnerabilities</label>
                    <div className="flex flex-wrap gap-2">
                      {[
                        { key: 'disabled', label: 'Disabled' },
                        { key: 'chronic_illness', label: 'Chronic' },
                        { key: 'pregnant', label: 'Pregnant' }
                      ].map((v) => (
                        <button
                          key={v.key}
                          type="button"
                          onClick={() => updateMember(member.id, { 
                            vulnerability: { 
                              ...member.vulnerability, 
                              [v.key]: !member.vulnerability[v.key as keyof typeof member.vulnerability] 
                            } 
                          })}
                          className={`px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-tight transition-all border ${
                            member.vulnerability[v.key as keyof typeof member.vulnerability]
                              ? 'bg-red-50 border-red-200 text-red-600'
                              : 'bg-white border-gray-100 text-gray-400'
                          }`}
                        >
                          {v.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Save Option for Identity Phase */}
        <div className="bg-brand-50 p-6 rounded-3xl border border-brand-100 mt-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-brand-600 rounded-full flex items-center justify-center text-white">
              <History className="w-5 h-5" />
            </div>
            <div>
              <h4 className="font-bold text-brand-900">Profile Snapshot</h4>
              <p className="text-xs text-brand-600">Sync these identity details to the household profile database.</p>
            </div>
          </div>
          <button 
            type="button"
            onClick={handleSaveIdentity}
            className="px-6 py-2 bg-brand-600 text-white rounded-xl text-sm font-bold shadow-sm hover:bg-brand-800 transition-all flex items-center gap-2"
          >
            <Package className="w-4 h-4" />
            Save Identity
          </button>
        </div>
      </motion.div>
    )}

        {step === 2 && (
          <motion.div 
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start pb-20"
          >
            <div className="lg:col-span-8 space-y-12">
              {/* Category Grid */}
              <section className="space-y-6">
                <div className="flex items-center justify-between">
                  <h2 className="font-headline text-2xl text-brand-900 italic">Need Category</h2>
                  <span className="text-[10px] font-mono text-gray-400 uppercase tracking-widest">Select Primary Need</span>
                </div>
                <div className="grid grid-cols-3 md:grid-cols-4 gap-3">
                  {CATEGORIES.map(cat => (
                    <button 
                      key={cat.id}
                      onClick={() => setSelectedCategory(cat.id)}
                      className={`p-6 rounded-2xl flex flex-col items-center gap-3 transition-all ${
                        selectedCategory === cat.id 
                        ? 'bg-brand-600 text-white shadow-lg scale-105' 
                        : 'bg-gray-50 text-gray-500 hover:bg-gray-100'
                      }`}
                    >
                      <cat.icon className={`w-8 h-8 ${selectedCategory === cat.id ? 'text-white' : 'text-brand-600'}`} />
                      <span className="text-[10px] font-bold uppercase tracking-tighter text-center">{cat.label}</span>
                    </button>
                  ))}
                </div>
                <div className="relative">
                  <label className="absolute -top-2 left-4 px-2 bg-background text-[10px] font-mono text-brand-600 font-bold uppercase tracking-widest">Subcategory</label>
                  <select 
                    value={subcategory}
                    onChange={(e) => setSubcategory(e.target.value)}
                    className="w-full bg-transparent border border-gray-200 rounded-xl px-6 py-4 font-headline text-lg italic text-brand-900 focus:ring-brand-400 focus:border-brand-400 appearance-none"
                  >
                    <option>Primary Care / Medical Consultation</option>
                    <option>Emergency Trauma Care</option>
                    <option>Maternal Health / OBGYN</option>
                    <option>Pediatric Specialization</option>
                  </select>
                </div>
              </section>

              {/* Description */}
              <section className="space-y-6">
                <div className="flex items-center justify-between">
                  <h2 className="font-headline text-2xl text-brand-900 italic">Need Description</h2>
                  <span className="px-3 py-1 rounded bg-brand-50 text-[10px] font-mono text-brand-600 flex items-center gap-2 uppercase tracking-widest font-bold">
                    <span className="w-1.5 h-1.5 rounded-full bg-brand-600 animate-pulse"></span>
                    Language Detected
                  </span>
                </div>
                <div className="space-y-4">
                  <textarea 
                    value={needDescription}
                    onChange={(e) => setNeedDescription(e.target.value)}
                    className="w-full bg-white border border-gray-100 rounded-2xl p-6 text-lg focus:ring-2 focus:ring-brand-400/20 placeholder:text-gray-300 shadow-sm"
                    placeholder="Detailed clinical observation or qualitative notes..."
                    rows={5}
                  />
                  <div className="bg-gray-50 rounded-2xl p-6 flex items-center justify-between gap-8">
                    <div className="flex items-center gap-4">
                      <button className="w-12 h-12 rounded-full bg-brand-600 text-white flex items-center justify-center hover:scale-105 active:scale-95 transition-transform shadow-md">
                        <Mic className="w-5 h-5" />
                      </button>
                      <div className="flex flex-col">
                        <span className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Voice Note</span>
                        <span className="font-headline italic text-sm text-brand-900">Start Recording</span>
                      </div>
                    </div>
                    <div className="flex-1 flex items-center gap-4">
                      <div className="flex-1 h-8 flex items-center gap-1 opacity-20">
                        {Array.from({length: 20}).map((_, i) => (
                          <div key={i} className="w-1 bg-brand-600 rounded-full" style={{ height: `${Math.random() * 100}%` }} />
                        ))}
                      </div>
                      <span className="font-mono text-sm text-brand-600 font-bold">0:32</span>
                    </div>
                  </div>
                </div>
              </section>

              {/* Severity & Impact */}
              <section className="space-y-10">
                <h2 className="font-headline text-2xl text-brand-900 italic">Severity & Impact</h2>
                <div className="space-y-12">
                  <div className="relative pt-6">
                    <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest block mb-4">Urgency Score</label>
                    <div className="relative w-full h-2 bg-gray-100 rounded-full">
                      <div 
                        className="absolute top-0 left-0 h-full bg-brand-600 rounded-full" 
                        style={{ width: `${urgencyScore * 100}%` }}
                      />
                      <div 
                        className="absolute top-1/2 -translate-y-12 -translate-x-1/2 transition-all duration-300"
                        style={{ left: `${urgencyScore * 100}%` }}
                      >
                        <div className="bg-brand-600 text-white font-mono text-sm px-3 py-1 rounded-full shadow-lg">
                          {urgencyScore.toFixed(2)} <span className="text-[8px] opacity-60">SCORE</span>
                        </div>
                      </div>
                      <input 
                        type="range"
                        min="0"
                        max="1"
                        step="0.01"
                        value={urgencyScore}
                        onChange={(e) => setUrgencyScore(parseFloat(e.target.value))}
                        className="absolute top-0 left-0 w-full h-2 opacity-0 cursor-pointer"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-12">
                    <div className="space-y-4">
                      <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Beneficiaries Affected</label>
                      <div className="flex items-center gap-6">
                        <button 
                          onClick={() => setBeneficiariesAffected(b => Math.max(1, b - 1))}
                          className="w-12 h-12 rounded-xl bg-gray-50 hover:bg-gray-100 flex items-center justify-center transition-colors"
                        >
                          <Minus className="w-5 h-5" />
                        </button>
                        <span className="font-headline text-4xl w-12 text-center text-brand-900">{beneficiariesAffected}</span>
                        <button 
                          onClick={() => setBeneficiariesAffected(b => b + 1)}
                          className="w-12 h-12 rounded-xl bg-gray-50 hover:bg-gray-100 flex items-center justify-center transition-colors"
                        >
                          <Plus className="w-5 h-5" />
                        </button>
                      </div>
                    </div>
                    <div className="space-y-4">
                      <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Information Source</label>
                      <div className="bg-gray-50 p-1.5 rounded-2xl flex gap-2">
                        {['In Person', 'Phone Call', 'Registry'].map(source => (
                          <button 
                            key={source}
                            onClick={() => setInfoSource(source)}
                            className={`flex-1 py-3 px-4 rounded-xl text-xs font-bold transition-all ${
                              infoSource === source 
                              ? 'bg-white text-brand-600 shadow-sm' 
                              : 'text-gray-400 hover:text-gray-600'
                            }`}
                          >
                            {source}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </section>

              {/* Observation context */}
              <section className="space-y-6 pt-6 border-t border-gray-100">
                <h2 className="font-headline text-2xl text-brand-900 italic">Observation Details</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div className="relative">
                    <label className="absolute -top-2 left-4 px-2 bg-background text-[10px] font-mono text-gray-400 font-bold uppercase tracking-widest">Assessment Date</label>
                    <input 
                      type="date"
                      value={assessmentDate}
                      onChange={(e) => setAssessmentDate(e.target.value)}
                      className="w-full bg-white border border-gray-100 rounded-xl px-6 py-4 font-headline text-lg text-brand-900 focus:ring-brand-400 focus:border-brand-400"
                    />
                  </div>
                  <div className="relative">
                    <label className="absolute -top-2 left-4 px-2 bg-background text-[10px] font-mono text-gray-400 font-bold uppercase tracking-widest">Local Time</label>
                    <input 
                      type="time"
                      value={localTime}
                      onChange={(e) => setLocalTime(e.target.value)}
                      className="w-full bg-white border border-gray-100 rounded-xl px-6 py-4 font-headline text-lg text-brand-900 focus:ring-brand-400 focus:border-brand-400"
                    />
                  </div>
                </div>
              </section>
            </div>

            {/* Sidebar Context */}
            <div className="lg:col-span-4 space-y-6">
              <div className="bg-white p-8 rounded-[2.5rem] border border-gray-100 shadow-xl shadow-brand-950/[0.03] space-y-6 sticky top-24">
                <div className="flex items-center gap-4">
                  <div className="w-16 h-16 rounded-2xl bg-brand-50 flex items-center justify-center text-brand-600 overflow-hidden">
                    <img 
                      src="https://images.unsplash.com/photo-1531123897727-8f129e1688ce?w=200&h=200&fit=crop" 
                      alt="HH"
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <div>
                    <h3 className="font-headline text-xl font-bold text-brand-900 italic">{isEditMode ? id : 'Aisha Al-Harbi'}</h3>
                    <p className="text-[10px] font-mono text-brand-600 font-bold uppercase tracking-widest">Case ID: #7719-TX</p>
                  </div>
                </div>
                <div className="space-y-4 border-t border-gray-50 pt-6">
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-[10px] font-bold text-gray-400 uppercase">Location</span>
                    <span className="font-headline italic text-brand-900">Zone 4, Sector B</span>
                  </div>
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-[10px] font-bold text-gray-400 uppercase">Members</span>
                    <span className="font-headline italic text-brand-900">{totalMembers} Total</span>
                  </div>
                </div>
                <div className="bg-brand-50 p-6 rounded-2xl space-y-3">
                  <div className="flex items-center gap-2">
                    <Shield className="w-4 h-4 text-brand-600" />
                    <span className="text-[10px] font-bold text-brand-600 uppercase tracking-widest">Intake Note</span>
                  </div>
                  <p className="text-xs italic font-headline leading-relaxed text-brand-900">
                    "Beneficiary reported mild respiratory distress during initial contact. Priority assessment required."
                  </p>
                </div>
                <div className="bg-gray-50 p-6 rounded-2xl space-y-4">
                  <h4 className="text-xs font-bold text-gray-900 uppercase">Reporting Guidelines</h4>
                  <ul className="space-y-2">
                    {['Focus on immediate physical needs.', 'Include specific medical terminology.'].map((rule, idx) => (
                      <li key={idx} className="flex gap-3 text-[11px] text-gray-500 leading-relaxed">
                        <div className="w-1 h-1 rounded-full bg-brand-600 mt-1.5 flex-shrink-0" />
                        {rule}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {step === 3 && (
          <motion.div 
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="space-y-8 pb-20"
          >
            <section className="bg-white p-10 rounded-[2.5rem] border border-gray-100 shadow-xl shadow-brand-950/[0.02] space-y-10">
              <div className="flex items-center justify-between border-b border-gray-50 pb-6">
                <div>
                  <h2 className="font-headline text-3xl text-brand-900 italic">Participation Consent</h2>
                  <p className="text-sm text-gray-500 mt-1 italic font-headline">Legal authorization for humanitarian assistance and data processing.</p>
                </div>
                <div className="bg-brand-50 p-3 rounded-2xl">
                  <Shield className="w-8 h-8 text-brand-600" />
                </div>
              </div>

              <div className="space-y-8">
                <div className="bg-gray-50 p-8 rounded-3xl space-y-4">
                  <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-[0.2em]">Mandatory Disclosure</h4>
                  <p className="text-sm border-l-2 border-brand-600 pl-6 leading-relaxed text-brand-900 font-headline italic">
                    "I hereby authorize the Clinical Sanctuary and its affiliated humanitarian partners to collect, store, and process my personal and household data for the sole purpose of assessing and delivering emergency aid. I understand this data may be shared with vetted third-party responders to facilitate rapid dispatch."
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  <div className="space-y-4">
                    <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Consent Method</label>
                    <div className="grid grid-cols-1 gap-3">
                      {['Verbal Affirmation', 'Physical Signature', 'Digital Thumbprint'].map(method => (
                        <button 
                          key={method}
                          type="button"
                          onClick={() => setConsentMethod(method)}
                          className={`flex items-center justify-between p-4 rounded-xl border transition-all ${
                            consentMethod === method 
                              ? 'border-brand-600 bg-brand-50 shadow-sm' 
                              : 'border-gray-100 hover:bg-gray-50'
                          }`}
                        >
                          <span className={`text-sm font-bold font-headline italic ${
                            consentMethod === method ? 'text-brand-600' : 'text-brand-900'
                          }`}>{method}</span>
                          <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all ${
                            consentMethod === method ? 'border-brand-600' : 'border-gray-200'
                          }`}>
                            {consentMethod === method && <div className="w-2.5 h-2.5 bg-brand-600 rounded-full" />}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="space-y-4">
                    <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Language of Disclosure</label>
                    <select 
                      value={consentLanguage}
                      onChange={(e) => setConsentLanguage(e.target.value)}
                      className="w-full bg-gray-50 border-none rounded-xl p-4 text-sm font-bold text-brand-900 font-headline italic focus:ring-2 focus:ring-brand-400/20"
                    >
                      <option>Arabic (Standard)</option>
                      <option>English</option>
                      <option>French</option>
                      <option>Local Dialect</option>
                    </select>
                    <div className="pt-4 space-y-6">
                      <div className="flex items-center justify-between">
                        <label className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Granular Data Scopes (DPDP)</label>
                        <span className="text-[9px] font-mono text-brand-600 bg-brand-50 px-2 py-0.5 rounded">Purpose-Limited</span>
                      </div>
                      
                      <div className="grid grid-cols-1 gap-4">
                        {PURPOSES.map(p => (
                          <button
                            key={p.id}
                            type="button"
                            onClick={() => toggleScope(p.id)}
                            className={cn(
                              "flex flex-col p-4 rounded-xl border text-left transition-all relative group",
                              permissionScopes.includes(p.id)
                                ? "bg-white border-brand-400 ring-1 ring-brand-400 shadow-md"
                                : "bg-gray-50 border-gray-100 opacity-60 hover:opacity-100"
                            )}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <span className={cn("text-[11px] font-bold uppercase", permissionScopes.includes(p.id) ? "text-brand-900" : "text-gray-500")}>
                                {p.label}
                              </span>
                              {p.essential && (
                                <span className="text-[8px] font-bold bg-amber-50 text-amber-600 px-1.5 py-0.5 rounded uppercase">Essential</span>
                              )}
                            </div>
                            <p className="text-[10px] leading-relaxed text-gray-500 line-clamp-1">{p.desc}</p>
                            {permissionScopes.includes(p.id) && (
                              <div className="absolute top-4 right-4 w-4 h-4 bg-brand-600 rounded-full flex items-center justify-center">
                                <CheckCircle className="w-2.5 h-2.5 text-white" />
                              </div>
                            )}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-brand-50 p-6 rounded-3xl flex items-center gap-6">
                <div className="w-14 h-14 rounded-full bg-white flex items-center justify-center text-brand-600 shadow-sm">
                  <Mic className="w-6 h-6" />
                </div>
                <div>
                  <h4 className="text-[10px] font-bold text-brand-600 uppercase tracking-widest">Audio Affirmation</h4>
                  <p className="text-xs text-brand-900 font-headline italic">Record the beneficiary's verbal 'I consent' for legal compliance.</p>
                </div>
                <button className="ml-auto px-6 py-2 bg-brand-600 text-white text-[10px] font-bold uppercase tracking-widest rounded-full shadow-lg shadow-brand-600/20">
                  Start Audio
                </button>
              </div>
            </section>
          </motion.div>
        )}

        {step === 4 && (
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-10 pb-32"
          >
            {/* Page Header */}
            <div className="mb-12">
              <h1 className="font-headline text-5xl font-medium tracking-tight mb-2 text-brand-900 italic">Final Review</h1>
              <p className="font-headline italic text-gray-500 text-lg">Validating intake parameters for humanitarian dispatch.</p>
            </div>

            {/* Green Auto-Match Banner */}
            <div className="bg-[#E8F5E9] border-l-4 border-[#2E7D32] p-6 rounded-r-2xl flex items-center justify-between shadow-sm">
              <div className="flex items-center gap-4">
                <div className="bg-[#2E7D32] text-white p-2 rounded-full">
                  <Shield className="w-4 h-4 shadow-sm" />
                </div>
                <div>
                  <p className="text-[#2E7D32] font-bold text-sm tracking-tight">
                    {isEditMode ? `Updating existing record ` : `New intake record validation successful `}
                    <span className="font-mono">{id || hhIdRef.current}</span>
                  </p>
                  <p className="text-[#2E7D32]/80 text-xs font-medium">Confidence Score: 1.00 (Verified Identity)</p>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
              <div className="lg:col-span-8 space-y-10">
                {/* Identity Summary Card */}
                <section className="bg-white rounded-3xl p-10 border border-gray-100 shadow-xl shadow-brand-950/[0.03] relative overflow-hidden">
                  <div className="absolute top-10 right-10">
                    <button 
                      onClick={() => setStep(1)}
                      className="text-brand-600 text-xs font-bold tracking-widest uppercase flex items-center gap-2 hover:opacity-70 transition-all"
                    >
                      <Plus className="w-4 h-4 rotate-45" /> Edit
                    </button>
                  </div>
                  <h2 className="font-headline text-2xl font-medium mb-8 border-b border-gray-50 pb-4 italic text-brand-900 text-left">Summary — Phase 1: Identity</h2>
                  <div className="grid grid-cols-2 gap-y-8 gap-x-12">
                    <div className="flex flex-col gap-1 text-left">
                      <span className="text-[10px] font-mono text-gray-400 uppercase tracking-widest font-bold">Organization</span>
                      <span className="font-headline italic text-brand-600 text-lg font-bold">
                        {selectedTenantName || 'Unknown Organization'}
                      </span>
                    </div>
                    <div className="flex flex-col gap-1 text-left">
                      <span className="text-[10px] font-mono text-gray-400 uppercase tracking-widest font-bold">HH ID</span>
                      <span className="font-mono font-bold text-brand-900">{id || 'NEW-RECORD'}</span>
                    </div>
                    <div className="flex flex-col gap-1 text-left">
                      <span className="text-[10px] font-mono text-gray-400 uppercase tracking-widest font-bold">Total Members</span>
                      <span className="font-headline italic text-brand-900 text-lg">{totalMembers} Individuals</span>
                    </div>
                    <div className="flex flex-col gap-1 text-left">
                      <span className="text-[10px] font-mono text-gray-400 uppercase tracking-widest font-bold">Dwelling Type</span>
                      <span className="font-headline italic text-brand-900 text-lg capitalize">{dwellingType}</span>
                    </div>
                    <div className="flex flex-col gap-1 text-left">
                      <span className="text-[10px] font-mono text-gray-400 uppercase tracking-widest font-bold">Economic Tier</span>
                      <span className="font-headline italic text-brand-900 text-lg">{economicTier}</span>
                    </div>
                    <div className="col-span-2 flex flex-col gap-1 pt-4 text-left">
                      <span className="text-[10px] font-mono text-gray-400 uppercase tracking-widest font-bold">Verbatim Location</span>
                      <p className="font-headline italic text-gray-600 text-xl leading-relaxed">"{locationDesc || 'No location description provided.'}"</p>
                    </div>
                    <div className="col-span-2 flex flex-col gap-2 text-left">
                      <span className="text-[10px] font-mono text-gray-400 uppercase tracking-widest font-bold">Landmark Tags</span>
                      <div className="flex flex-wrap gap-2 pt-1">
                        {['#BlueWaterTank', '#Sector4_West', '#TentedSettlement'].map(tag => (
                          <span key={tag} className="bg-gray-50 border border-gray-100 px-3 py-1.5 rounded-lg text-[11px] font-bold text-gray-500 uppercase tracking-tight">
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                </section>

                {/* Need Summary Card */}
                <section className="bg-white rounded-3xl p-10 border border-gray-100 shadow-xl shadow-brand-950/[0.03] relative">
                  <div className="absolute top-10 right-10">
                    <button 
                      onClick={() => setStep(2)}
                      className="text-brand-600 text-xs font-bold tracking-widest uppercase flex items-center gap-2 hover:opacity-70 transition-all"
                    >
                      <Plus className="w-4 h-4 rotate-45" /> Edit
                    </button>
                  </div>
                  <h2 className="font-headline text-2xl font-medium mb-8 border-b border-gray-50 pb-4 italic text-brand-900 text-left">Summary — Phase 2: Need</h2>
                  <div className="space-y-10">
                    <div className="flex items-start gap-8 text-left">
                      <div className="bg-[#E8916A]/10 text-[#E8916A] p-5 rounded-2xl shadow-sm">
                        {(() => {
                          const Icon = CATEGORIES.find(c => c.id === selectedCategory)?.icon || Heart;
                          return <Icon className="w-10 h-10" />;
                        })()}
                      </div>
                      <div className="flex-1">
                        <div className="flex justify-between items-center mb-3">
                          <h3 className="font-headline text-2xl font-medium italic text-brand-900 capitalize">
                            {CATEGORIES.find(c => c.id === selectedCategory)?.label || selectedCategory}
                          </h3>
                          <span className="bg-red-50 text-red-600 text-[10px] font-mono px-3 py-1 rounded border border-red-100 font-bold uppercase tracking-[0.2em]">Urgent Intake</span>
                        </div>
                        <p className="font-headline italic text-gray-600 leading-relaxed text-xl">
                          "{needDescription || 'Significant interruption in clean water access for the last 48 hours. Three children under five showing signs of dehydration.'}"
                        </p>
                      </div>
                    </div>

                    <div className="bg-gray-50 p-8 rounded-2xl flex items-center justify-between border border-gray-100/50">
                      <div className="flex flex-col text-left">
                        <span className="text-[10px] font-mono text-gray-400 uppercase tracking-[0.2em] font-bold mb-3">Local Urgency Rating</span>
                        <div className="flex items-center gap-4">
                          <div className="w-40 h-2 bg-gray-200 rounded-full overflow-hidden">
                            <div className="h-full bg-red-500 rounded-full" style={{ width: `${urgencyScore * 100}%` }}></div>
                          </div>
                          <span className="font-mono text-lg font-bold text-red-600">{urgencyScore.toFixed(2)}</span>
                        </div>
                      </div>
                      <div className="text-right">
                        <span className="text-[10px] font-mono text-gray-400 uppercase tracking-[0.2em] font-bold mb-1">Beneficiaries</span>
                        <p className="font-headline italic font-bold text-2xl text-brand-900">{totalMembers} Individuals</p>
                      </div>
                    </div>

                    {/* Voice Recording Playback */}
                    <div className="bg-brand-900 text-white p-6 rounded-2xl flex items-center gap-6 shadow-lg shadow-brand-900/10">
                      <button className="bg-white text-brand-900 w-14 h-14 rounded-full flex items-center justify-center hover:scale-105 active:scale-95 transition-all shadow-md">
                        <div className="w-0 h-0 border-t-[10px] border-t-transparent border-l-[16px] border-l-brand-900 border-b-[10px] border-b-transparent ml-1.5" />
                      </button>
                      <div className="flex-1">
                        <div className="flex justify-between text-[11px] font-mono uppercase opacity-50 mb-3 tracking-widest font-bold">
                          <span>Voice Recording: Field Intake</span>
                          <span>0:24 / 1:12</span>
                        </div>
                        <div className="h-10 flex items-end gap-1.5">
                          {Array.from({length: 40}).map((_, i) => (
                            <div 
                              key={i} 
                              className={`w-1 rounded-full transition-all duration-300 ${i < 12 ? 'bg-white opacity-100' : 'bg-white/30'}`} 
                              style={{ height: `${20 + Math.random() * 80}%` }}
                            />
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                </section>

                {/* Consent Summary Card */}
                <section className="bg-white rounded-3xl p-10 border border-gray-100 shadow-xl shadow-brand-950/[0.03] relative">
                  <div className="absolute top-10 right-10">
                    <button 
                      onClick={() => setStep(3)}
                      className="text-brand-600 text-xs font-bold tracking-widest uppercase flex items-center gap-2 hover:opacity-70 transition-all"
                    >
                      <Plus className="w-4 h-4 rotate-45" /> Edit
                    </button>
                  </div>
                  <h2 className="font-headline text-2xl font-medium mb-8 border-b border-gray-50 pb-4 italic text-brand-900 text-left">Summary — Phase 3: Consent</h2>
                  <div className="grid grid-cols-2 gap-12 mb-12">
                    <div className="space-y-6">
                      <div className="flex flex-col gap-1 text-left">
                        <span className="text-[10px] font-mono text-gray-400 uppercase tracking-widest font-bold">Provider</span>
                        <span className="font-headline italic text-brand-900 text-lg">Al-Khairi Humanitarian Assoc.</span>
                      </div>
                      <div className="flex flex-col gap-1 text-left">
                        <span className="text-[10px] font-mono text-gray-400 uppercase tracking-widest font-bold">Method</span>
                        <span className="font-headline italic text-brand-900 text-lg">{consentMethod} (Witnessed)</span>
                      </div>
                    </div>
                    <div className="space-y-6">
                      <div className="flex flex-col gap-1 text-left">
                        <span className="text-[10px] font-mono text-gray-400 uppercase tracking-widest font-bold">Language</span>
                        <span className="font-headline italic text-brand-900 text-lg font-bold">{consentLanguage}</span>
                      </div>
                      <div className="flex flex-col gap-1 text-left">
                        <span className="text-[10px] font-mono text-gray-400 uppercase tracking-widest font-bold">Valid Until</span>
                        <span className="font-mono font-bold text-brand-600 text-lg">2026-12-31</span>
                      </div>
                    </div>
                  </div>
                  <div className="bg-gray-50/50 rounded-[2rem] p-8 border border-gray-100 mt-6">
                    <h4 className="text-[11px] font-mono text-gray-400 uppercase tracking-[0.2em] font-bold mb-6">Authorized Permission Scopes</h4>
                    <div className="flex flex-wrap gap-2 text-left">
                      {permissionScopes.length > 0 ? (
                        permissionScopes.map(scope => (
                          <span key={scope} className="bg-brand-50 text-brand-700 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-tight border border-brand-100 flex items-center gap-2">
                             <div className="w-1.5 h-1.5 rounded-full bg-brand-600"></div>
                             {scope}
                          </span>
                        ))
                      ) : (
                        <span className="text-gray-400 italic text-xs font-headline">No scopes authorized</span>
                      )}
                    </div>
                  </div>
                </section>
              </div>

              {/* Sidebar Projections */}
              <aside className="lg:col-span-4 space-y-10">
                <section className="bg-brand-600 text-white rounded-[3rem] p-10 shadow-2xl shadow-brand-600/20 relative overflow-hidden text-left sticky top-10">
                  <div className="relative z-10">
                    <span className="text-[10px] font-mono uppercase tracking-[0.3em] opacity-60 font-bold">Unified Priority Index</span>
                    <div className="flex items-baseline gap-3 mt-6">
                      <span className="font-mono text-7xl font-bold tracking-tighter">{urgencyScore.toFixed(2)}</span>
                      <span className="text-white/60 font-headline text-2xl italic tracking-tight">/ {urgencyScore > 0.7 ? 'High Priority' : urgencyScore > 0.4 ? 'Medium Priority' : 'Routine'}</span>
                    </div>
                    <div className="space-y-8 mt-12 pb-8 border-b border-white/10">
                      {[
                        { label: 'Severity', val: urgencyScore.toFixed(2) },
                        { label: 'Vulnerability', val: dwellingType === 'makeshift' ? 0.95 : dwellingType === 'katcha' ? 0.85 : 0.65 },
                        { label: 'Recency', val: 0.98 }
                      ].map(stat => (
                        <div key={stat.label} className="space-y-3">
                          <div className="flex justify-between text-[10px] font-mono font-bold uppercase tracking-[0.2em]">
                            <span>{stat.label}</span>
                            <span className="opacity-60">{stat.val}</span>
                          </div>
                          <div className="h-1.5 bg-white/20 rounded-full overflow-hidden">
                            <div className="h-full bg-white shadow-[0_0_8px_rgba(255,255,255,0.5)]" style={{ width: `${Number(stat.val) * 100}%` }}></div>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="pt-8">
                      <p className="text-[13px] leading-relaxed opacity-80 italic font-headline antialiased">
                        "Projecting a critical window of 12-24 hours before escalation to 'Crisis' level based on sector-wide WASH metrics."
                      </p>
                    </div>
                  </div>
                </section>
                
                <div className="bg-gray-50 p-10 rounded-[2.5rem] space-y-8 border border-gray-100 shadow-sm">
                  <h4 className="text-[10px] font-mono text-gray-400 uppercase tracking-[0.2em] font-bold">Intake Metadata</h4>
                  <div className="space-y-6">
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-gray-400 font-medium">Assigned to:</span>
                      <span className="font-bold text-brand-900 font-headline italic text-base">Alex Chen (Field Unit 4)</span>
                    </div>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-gray-400 font-medium">Captured via:</span>
                      <span className="font-bold text-brand-900 font-headline italic text-base">Direct Interview</span>
                    </div>
                    <div className="flex justify-between items-center text-sm">
                      <span className="text-gray-400 font-medium">Time Latency:</span>
                      <span className="font-mono text-[#2E7D32] bg-[#E8F5E9] px-3 py-1 rounded-full text-xs font-bold tracking-tight">04m 12s (Real-time)</span>
                    </div>
                  </div>
                </div>
              </aside>
            </div>

            {/* Bottom Actions for Step 4 */}
            <div className="fixed bottom-0 left-0 w-full bg-white/90 backdrop-blur-xl border-t border-gray-100/50 z-50 py-8">
              <div className="max-w-5xl mx-auto flex items-center justify-between px-6">
                <button 
                  onClick={() => setStep(3)}
                  className="flex items-center gap-3 text-brand-900 font-bold uppercase tracking-[0.2em] text-[11px] hover:bg-gray-50 px-8 py-4 rounded-full transition-all active:scale-95 border border-transparent hover:border-gray-100"
                >
                  <ArrowRight className="w-4 h-4 rotate-180" />
                  Back to Consent
                </button>
                <button 
                  onClick={handleSubmit}
                  disabled={isSubmitting}
                  className={cn(
                    "bg-[#2E7D32] text-white font-bold uppercase tracking-[0.2em] text-xs flex items-center gap-4 px-12 py-5 rounded-full shadow-2xl transition-all active:scale-90",
                    isSubmitting ? "opacity-70 cursor-not-allowed" : "shadow-[#2E7D32]/30 hover:bg-[#2E7D32]/90"
                  )}
                >
                  {isSubmitting ? 'Submitting...' : 'Submit Need Report'}
                  <div className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center">
                    {isSubmitting ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
                  </div>
                </button>
              </div>
            </div>
          </motion.div>
        )}
        {/* Footer actions - Hidden in Step 4 as it has fixed footer */}
        {step !== 4 && (
          <div className="flex justify-between items-center pt-8 border-t border-gray-100">
            <button 
              type="button"
              onClick={() => step > 1 ? setStep((step - 1) as Step) : navigate('/households')}
              className="px-8 py-3 rounded-xl text-gray-500 font-bold text-sm hover:bg-gray-100 transition-colors"
            >
              {step === 1 ? 'Cancel & Exit' : 'Back to Identity'}
            </button>
            <div className="flex gap-4">
              <button 
                onClick={handleSaveIdentity}
                className="px-8 py-3 rounded-xl bg-gray-100 text-gray-900 font-bold text-sm hover:bg-gray-200 transition-colors"
              >
                Save Draft
              </button>
              <button 
                onClick={() => setStep((step + 1) as Step)}
                className="px-10 py-3 rounded-xl bg-brand-600 text-white font-bold text-sm hover:bg-brand-800 transition-all shadow-md flex items-center gap-2"
              >
                Proceed to {step === 1 ? 'Needs' : step === 2 ? 'Consent' : 'Review'}
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

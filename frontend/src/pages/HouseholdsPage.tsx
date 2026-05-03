import React, { useState, useEffect } from 'react';
import { cn } from '../lib/utils';
import { useUiStore } from '../stores/ui.store';
import { useHouseholdStore } from '../stores/household.store';
import { Search, Home, ShieldAlert, Plus, Pencil, Trash2, Loader2 } from 'lucide-react';
import { useAuthStore } from '../stores/auth.store';
import { useTenantStore } from '../stores/tenant.store';
import { TenantSelector } from '../components/TenantSelector';
import { HouseholdDetailDrawer } from '../components/households/HouseholdDetailDrawer';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import { HouseholdAPI, NeedAPI } from '../api/endpoints';
import { 
  prepareHouseholdPayload, 
  prepareNeedPayload, 
  prepareConsentPayload 
} from '../lib/intakeMappings';

export function HouseholdsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { activePanel, panelReferenceId, openPanel } = useUiStore();
  const { households, isLoading, fetchHouseholds, searchHouseholds, deleteHousehold } = useHouseholdStore();
  const [searchTerm, setSearchTerm] = useState(searchParams.get('search') || '');
  const [mergeTargetId, setMergeTargetId] = useState('');
  const [activeTab, setActiveTab] = useState<'records' | 'drafts'>('records');
  const [drafts, setDrafts] = useState<any[]>([]);

  useEffect(() => {
    fetchHouseholds();
    const storedDrafts = JSON.parse(localStorage.getItem('nexus_drafts') || '[]');
    setDrafts(storedDrafts);
  }, []);

  useEffect(() => {
    fetchHouseholds();
  }, []);

  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      if (searchTerm) {
        searchHouseholds(searchTerm);
      } else {
        fetchHouseholds();
      }
    }, 500);

    return () => clearTimeout(delayDebounceFn);
  }, [searchTerm, searchHouseholds, fetchHouseholds]);

  const { role } = useAuthStore();
  const { tenant_id: currentTenantId, tenant_name: currentTenantName, setTenant } = useTenantStore();

  const handleTenantChange = (tenant: any) => {
    setTenant(tenant.tenant_id, tenant.slug, tenant.name);
    fetchHouseholds();
  };

  const filtered = households;

  const handleDelete = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (confirm('Are you sure you want to delete this household record? This action cannot be undone.')) {
      deleteHousehold(id);
      toast.success(`Household ${id} deleted successfully`);
    }
  };

  const handleEdit = (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    navigate(`/households/intake/${id}`);
  };

  const handleDeleteDraft = (e: React.MouseEvent, draftId: string) => {
    e.stopPropagation();
    if (confirm('Are you sure you want to discard this draft?')) {
      const updatedDrafts = drafts.filter(d => d.draftId !== draftId);
      setDrafts(updatedDrafts);
      localStorage.setItem('nexus_drafts', JSON.stringify(updatedDrafts));
      toast.success('Draft deleted successfully');
    }
  };

  const handleResumeDraft = (e: React.MouseEvent, draftId: string) => {
    e.stopPropagation();
    navigate(`/households/intake?draftId=${draftId}`);
  };

  const handleDirectSubmit = async (e: React.MouseEvent, draft: any) => {
    e.stopPropagation();
    if (!confirm('Submit this draft record immediately?')) return;

    const toastId = toast.loading('Submitting draft record...');
    try {
      // Restore tenant context if it exists in the draft (crucial for platform_admins)
      if (draft.tenant_id) {
        const { setTenant } = (await import('../stores/tenant.store')).useTenantStore.getState();
        // Force the tenant context for the submission
        setTenant(draft.tenant_id, '', '');
      } else {
        // Fallback for legacy drafts: ensure at least some tenant is set from the store
        const currentTenantId = (await import('../stores/tenant.store')).useTenantStore.getState().tenant_id;
        if (!currentTenantId) {
          toast.update(toastId, { 
            render: 'Organization Required: This draft is missing organization context. Please click "Resume Draft", select an organization, and Save.', 
            type: 'error', 
            isLoading: false, 
            autoClose: 8000 
          });
          return;
        }
      }

      // 1. Create Household
      const hhPayload = prepareHouseholdPayload(draft);
      const hhRes = await HouseholdAPI.create(hhPayload);
      const finalHouseholdId = hhRes.data.household_id;

      // 2. Submit Need (if any)
      const needPayload = prepareNeedPayload(draft, finalHouseholdId);
      if (needPayload) {
        await NeedAPI.ingestMobile(needPayload);
      }

      // 3. Add Consent (if any)
      const consentPayload = prepareConsentPayload(draft);
      if (consentPayload) {
        await HouseholdAPI.addConsent(finalHouseholdId, consentPayload);
      }

      // 4. Cleanup
      const updatedDrafts = drafts.filter(d => d.draftId !== draft.draftId);
      setDrafts(updatedDrafts);
      localStorage.setItem('nexus_drafts', JSON.stringify(updatedDrafts));

      toast.update(toastId, { 
        render: 'Record submitted successfully!', 
        type: 'success', 
        isLoading: false, 
        autoClose: 3000 
      });
      
      fetchHouseholds();
      setActiveTab('records');
    } catch (err: any) {
      toast.update(toastId, { 
        render: err?.response?.data?.detail || 'Submission failed', 
        type: 'error', 
        isLoading: false, 
        autoClose: 5000 
      });
    }
  };

  const handleMerge = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    const target = window.prompt(`Merge ${id} INTO which household ID?`);
    if (target && target !== id) {
      const reason = window.prompt('Merge reason?');
      if (reason) {
        try {
          const { HouseholdAPI } = await import('../api/endpoints');
          await HouseholdAPI.merge({ source_id: id, target_id: target, reason });
          toast.success(`Household ${id} merged into ${target}`);
          fetchHouseholds();
        } catch (err) {
          toast.error('Failed to merge households');
        }
      }
    }
  };

  return (
    <div className="flex flex-col h-full relative">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h2 className="text-2xl font-headline font-semibold text-brand-900">Household Profiles</h2>
          <p className="text-sm text-gray-500 mt-1">Manage and track household vulnerability and assistance.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex bg-white border border-warm-border rounded-xl overflow-hidden relative max-w-xs w-full shadow-sm">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input 
              type="text"
              placeholder="Search HH-ID or Location..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-9 pr-4 py-2 text-sm w-full focus:outline-none"
            />
          </div>
          <button 
            onClick={() => navigate('/households/intake')}
            className="flex items-center gap-2 bg-brand-600 text-white px-4 py-2 rounded-xl text-sm font-bold shadow-sm hover:bg-brand-800 transition-all"
          >
            <Plus className="w-4 h-4" /> New Intake
          </button>
        </div>
      </div>

      <div className="flex items-center gap-4 mb-6 border-b border-gray-200">
        <button
          onClick={() => setActiveTab('records')}
          className={`px-4 py-2 font-bold text-sm border-b-2 transition-colors ${
            activeTab === 'records' ? 'border-brand-600 text-brand-600' : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Submitted Records ({filtered.length})
        </button>
        <button
          onClick={() => setActiveTab('drafts')}
          className={`px-4 py-2 font-bold text-sm border-b-2 transition-colors ${
            activeTab === 'drafts' ? 'border-brand-600 text-brand-600' : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Saved Drafts ({drafts.length})
        </button>
      </div>

      {isLoading && households.length === 0 ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-8 h-8 text-brand-600 animate-spin" />
          <span className="ml-3 text-gray-500">Loading households...</span>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pb-10">
          {activeTab === 'records' && filtered.map(hh => (
            <div 
              key={hh.household_id} 
              onClick={() => openPanel('household_details', hh.household_id)}
              className="bg-white p-6 rounded-3xl border border-warm-border hover:border-brand-400 hover:ring-1 hover:ring-brand-400 cursor-pointer transition-all shadow-sm flex flex-col group relative"
            >
              {/* Existing record rendering... it was partially replaced above, so I need to preserve the render */}
              {/* Actually, I am replacing the map function entirely just to conditionally render it */}
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-brand-50 text-brand-600 rounded">
                    <Home className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-bold text-gray-900 truncate max-w-[150px]">
                      {hh.display_name || `HH-${hh.household_id?.slice(0, 5) || '?????'}`}
                    </h3>
                    <div className="flex flex-col">
                      <span className="text-[10px] text-gray-400 font-mono">{hh.household_id?.slice(0, 13) || 'ID missing'}...</span>
                      <span className="text-xs text-brand-600 font-bold">{hh.total_members} Members</span>
                    </div>
                  </div>
                </div>
                <div className="flex flex-col items-end">
                  <div className="flex gap-2 mb-2">
                    <button 
                      onClick={(e) => handleEdit(e, hh.household_id)}
                      className="px-2 py-1 bg-brand-50 hover:bg-brand-100 text-brand-700 border border-brand-200 rounded-lg transition-colors text-xs font-bold flex items-center gap-1"
                      title="Update Record"
                    >
                      <Pencil className="w-3 h-3" /> Update
                    </button>
                    <button 
                      onClick={(e) => handleMerge(e, hh.household_id)}
                      className="p-1 hover:bg-blue-50 text-blue-500 rounded-lg transition-colors"
                      title="Merge Record"
                    >
                      <span className="text-[10px] font-bold">MERGE</span>
                    </button>
                    <button 
                      onClick={(e) => handleDelete(e, hh.household_id)}
                      className="px-2 py-1 bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 rounded-lg transition-colors text-xs font-bold flex items-center gap-1"
                      title="Delete Record"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                  <div className="flex flex-col gap-1 mt-1 items-end">
                    <span className={`text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded ${
                      hh.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                    }`}>
                      {hh.status}
                    </span>
                    <div className={cn(
                      "text-[10px] font-bold px-2 py-0.5 rounded flex items-center gap-1",
                      hh.vulnerability_score > 0.7 ? "bg-red-100 text-red-700" :
                      hh.vulnerability_score > 0.4 ? "bg-amber-100 text-amber-700" : "bg-blue-100 text-blue-700"
                    )}>
                      <ShieldAlert className="w-3 h-3" />
                      {hh.vulnerability_score > 0.7 ? "High Severity" :
                       hh.vulnerability_score > 0.4 ? "Mid Severity" : "Low Severity"}
                    </div>
                  </div>
                </div>
              </div>

              <p className="text-sm text-gray-600 line-clamp-2 mt-2 flex-grow">
                {hh.location_description || 'No location description'}
              </p>

              <div className="mt-4 pt-3 border-t border-warm-border text-xs text-gray-500 flex justify-between">
                <span>Ward: {hh.ward_id || 'N/A'}</span>
                <span className="font-mono">Score: {(hh.vulnerability_score || 0).toFixed(2)}</span>
              </div>
              
            </div>
          ))}
          {activeTab === 'records' && filtered.length === 0 && !isLoading && (
            <div className="col-span-full text-center py-16 text-gray-400">
              <Home className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="font-medium">No households found</p>
              <p className="text-sm mt-1">Try adjusting your search or register a new intake.</p>
            </div>
          )}

          {activeTab === 'drafts' && drafts.map(draft => (
            <div 
              key={draft.draftId}
              className="bg-orange-50 p-6 rounded-3xl border border-orange-200 hover:border-orange-400 hover:ring-1 hover:ring-orange-400 cursor-pointer transition-all shadow-sm flex flex-col relative"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-orange-100 text-orange-600 rounded">
                    <Pencil className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-bold text-gray-900 truncate max-w-[150px]">
                      {draft.display_name || (draft.members?.[0]?.name) || 'Unnamed Draft'}
                    </h3>
                    <span className="text-xs text-orange-600 font-bold">Saved: {new Date(draft.lastSaved).toLocaleDateString()}</span>
                  </div>
                </div>
                <div className="flex flex-col items-end">
                  <div className="flex gap-2 mb-2">
                    <button 
                      onClick={(e) => handleDirectSubmit(e, draft)}
                      className="px-2 py-1 bg-green-600 hover:bg-green-700 text-white border border-green-700 rounded-lg transition-colors text-xs font-bold flex items-center gap-1"
                      title="Submit Now"
                    >
                      Submit
                    </button>
                    <button 
                      onClick={(e) => handleResumeDraft(e, draft.draftId)}
                      className="px-2 py-1 bg-brand-50 hover:bg-brand-100 text-brand-700 border border-brand-200 rounded-lg transition-colors text-xs font-bold flex items-center gap-1"
                      title="Resume Draft"
                    >
                      Resume
                    </button>
                    <button 
                      onClick={(e) => handleDeleteDraft(e, draft.draftId)}
                      className="px-2 py-1 bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 rounded-lg transition-colors text-xs font-bold flex items-center gap-1"
                      title="Discard Draft"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                  <span className="text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded bg-orange-200 text-orange-800">
                    Draft (Step {draft.step})
                  </span>
                </div>
              </div>

              <p className="text-sm text-gray-600 line-clamp-2 mt-2 flex-grow">
                {draft.location_description || 'No location description'}
              </p>

              <div className="mt-4 pt-3 border-t border-orange-200/50 text-xs text-gray-500 flex justify-between">
                <span>Members: {draft.total_members || 1}</span>
                <span className="font-mono">{draft.ward_id || 'N/A'}</span>
              </div>
            </div>
          ))}
          {activeTab === 'drafts' && drafts.length === 0 && (
            <div className="col-span-full text-center py-16 text-gray-400">
              <Pencil className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p className="font-medium">No saved drafts</p>
              <p className="text-sm mt-1">Start a new intake and click "Save Draft" to see it here.</p>
            </div>
          )}
        </div>
      )}

      {activePanel === 'household_details' && panelReferenceId && (
        <HouseholdDetailDrawer householdId={panelReferenceId} />
      )}
    </div>
  );
}

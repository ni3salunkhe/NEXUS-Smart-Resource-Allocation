import React, { useState, useEffect } from 'react';
import { Shield, Plus, Search, Building2, ExternalLink, Mail, Trash2, CheckCircle2 } from 'lucide-react';
import { apiClient } from '../lib/axios';
import { toast } from 'react-hot-toast';

interface Tenant {
  tenant_id: string;
  name: string;
  slug: string;
  contact_email: string;
  plan_tier: string;
  created_at: string;
}

export function AdminTenantsPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [search, setSearch] = useState('');
  
  const [newTenant, setNewTenant] = useState({
    name: '',
    slug: '',
    contact_email: '',
    plan_tier: 'standard'
  });

  useEffect(() => {
    fetchTenants();
  }, []);

  const fetchTenants = async () => {
    setIsLoading(true);
    try {
      // Note: We need a GET /tenants endpoint on the backend.
      const res = await apiClient.get('/api/proxy/tenants');
      if (Array.isArray(res.data)) {
        setTenants(res.data);
      } else {
        throw new Error('Invalid response format');
      }
    } catch (err) {
      toast.error('Failed to load organizations');
      // Mock data for now to show the UI
      setTenants([
        { 
          tenant_id: '1', 
          name: 'Asha Welfare Trust', 
          slug: 'default', 
          contact_email: 'admin@asha.org', 
          plan_tier: 'enterprise',
          created_at: new Date().toISOString()
        }
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsCreating(true);
    try {
      await apiClient.post('/api/proxy/tenants', newTenant);
      toast.success('Organization created successfully');
      setIsCreating(false);
      setNewTenant({ name: '', slug: '', contact_email: '', plan_tier: 'standard' });
      fetchTenants();
    } catch (err) {
      toast.error('Creation failed. Check if slug is unique.');
    } finally {
      setIsCreating(false);
    }
  };

  const filteredTenants = tenants.filter(t => 
    t.name.toLowerCase().includes(search.toLowerCase()) || 
    t.slug.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="flex flex-col h-full bg-slate-50 p-8 space-y-8 overflow-y-auto pb-20">
      
      {/* Header section */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold text-slate-900 tracking-tight flex items-center gap-3">
            <Building2 className="w-10 h-10 text-brand-600" />
            Organizations
          </h1>
          <p className="text-slate-500 mt-2 font-medium">Manage and onboard humanitarian partners to the NEXUS network.</p>
        </div>
        
        <div className="flex items-center gap-3">
           <div className="relative group">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 group-focus-within:text-brand-600 transition-colors" />
              <input 
                type="text" 
                placeholder="Search NGOs..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-11 pr-6 py-3 bg-white border border-warm-border rounded-2xl text-sm focus:outline-none focus:border-brand-600 shadow-sm w-64 transition-all"
              />
           </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Left: Organization List */}
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-white rounded-[32px] border border-warm-border shadow-sm overflow-hidden">
             <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-50/50 border-bottom border-slate-100">
                    <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Organization</th>
                    <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Slug</th>
                    <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Tier</th>
                    <th className="px-6 py-4 text-[10px] font-bold text-slate-400 uppercase tracking-widest">Created</th>
                    <th className="px-6 py-4"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {filteredTenants.map(tenant => (
                    <tr key={tenant.tenant_id} className="hover:bg-slate-50/30 transition-colors group">
                      <td className="px-6 py-5">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 bg-brand-50 rounded-xl flex items-center justify-center text-brand-600">
                            <Building2 className="w-5 h-5" />
                          </div>
                          <div>
                            <p className="font-bold text-slate-900">{tenant.name}</p>
                            <p className="text-xs text-slate-400">{tenant.contact_email}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-5">
                        <code className="text-xs font-mono bg-slate-100 px-2 py-1 rounded text-slate-600">{tenant.slug}</code>
                      </td>
                      <td className="px-6 py-5">
                        <span className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase ${
                          tenant.plan_tier === 'enterprise' ? 'bg-indigo-100 text-indigo-700' : 'bg-emerald-100 text-emerald-700'
                        }`}>
                          {tenant.plan_tier}
                        </span>
                      </td>
                      <td className="px-6 py-5 text-sm text-slate-400">
                        {new Date(tenant.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-5 text-right">
                        <button className="p-2 text-slate-300 hover:text-brand-600 transition-colors opacity-0 group-hover:opacity-100">
                          <ExternalLink className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
             </table>
             {filteredTenants.length === 0 && !isLoading && (
               <div className="p-20 text-center">
                  <Building2 className="w-12 h-12 text-slate-200 mx-auto mb-4" />
                  <p className="text-slate-500 font-medium">No organizations found</p>
               </div>
             )}
          </div>
        </div>

        {/* Right: Create Form */}
        <div className="space-y-6">
          <div className="bg-slate-900 rounded-[32px] p-8 text-white shadow-2xl relative overflow-hidden">
            <div className="absolute top-[-50px] right-[-50px] w-48 h-48 bg-brand-500 rounded-full blur-[80px] opacity-20"></div>
            
            <h3 className="text-xl font-bold mb-6 flex items-center gap-2">
              <Plus className="w-5 h-5 text-brand-400" />
              Onboard Partner
            </h3>

            <form onSubmit={handleCreate} className="space-y-5 relative">
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2 px-1">Organization Name</label>
                <input 
                  type="text" 
                  required
                  placeholder="e.g. Red Cross India"
                  value={newTenant.name}
                  onChange={e => setNewTenant({...newTenant, name: e.target.value})}
                  className="w-full px-5 py-3 bg-white/10 border border-white/10 rounded-2xl text-sm focus:outline-none focus:border-brand-400 focus:bg-white/20 transition-all placeholder:text-white/30"
                />
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2 px-1">Domain Slug</label>
                <div className="relative">
                  <input 
                    type="text" 
                    required
                    placeholder="red-cross"
                    value={newTenant.slug}
                    onChange={e => setNewTenant({...newTenant, slug: e.target.value.toLowerCase().replace(/ /g, '-')})}
                    className="w-full px-5 py-3 bg-white/10 border border-white/10 rounded-2xl text-sm focus:outline-none focus:border-brand-400 focus:bg-white/20 transition-all placeholder:text-white/30"
                  />
                  <Shield className="absolute right-4 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/20" />
                </div>
                <p className="text-[9px] text-slate-500 mt-2 px-1 italic">This is used for URL and tenant isolation (e.g. nexus.org/t/slug)</p>
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2 px-1">Contact Email</label>
                <div className="relative">
                  <input 
                    type="email" 
                    required
                    placeholder="ops@organization.org"
                    value={newTenant.contact_email}
                    onChange={e => setNewTenant({...newTenant, contact_email: e.target.value})}
                    className="w-full px-5 py-3 bg-white/10 border border-white/10 rounded-2xl text-sm focus:outline-none focus:border-brand-400 focus:bg-white/20 transition-all placeholder:text-white/30"
                  />
                  <Mail className="absolute right-4 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-white/20" />
                </div>
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2 px-1">Plan Tier</label>
                <select 
                  value={newTenant.plan_tier}
                  onChange={e => setNewTenant({...newTenant, plan_tier: e.target.value})}
                  className="w-full px-5 py-3 bg-white/10 border border-white/10 rounded-2xl text-sm focus:outline-none focus:border-brand-400 focus:bg-white/20 transition-all"
                >
                  <option value="standard" className="text-slate-900">Standard NGOs</option>
                  <option value="enterprise" className="text-slate-900">Government/UN Partners</option>
                </select>
              </div>

              <button 
                type="submit"
                disabled={isCreating}
                className="w-full bg-brand-600 text-white font-bold py-4 rounded-2xl shadow-xl shadow-brand-900/40 hover:bg-brand-500 transition-all active:scale-[0.98] disabled:opacity-50 mt-2"
              >
                {isCreating ? 'Provisioning...' : 'Initialize Organization'}
              </button>
            </form>
          </div>

          <div className="bg-white rounded-[32px] p-6 border border-warm-border shadow-sm">
             <h4 className="font-bold text-slate-900 mb-4 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                Onboarding Protocol
             </h4>
             <ul className="space-y-3">
                {[
                  'Automatic DB Schema Isolation',
                  'Dedicated Kafka Ingestion Pipeline',
                  'Urgency Weights Seeded',
                  'Initial NGO Admin Credentials generated'
                ].map((item, i) => (
                  <li key={i} className="flex gap-3 text-xs text-slate-500 leading-tight">
                    <span className="w-4 h-4 bg-slate-100 rounded-full flex-shrink-0 flex items-center justify-center text-[10px] font-bold">{i+1}</span>
                    {item}
                  </li>
                ))}
             </ul>
          </div>
        </div>

      </div>
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { Search, Building2, Check, ChevronDown, Loader2, Plus } from 'lucide-react';
import { TenantAPI } from '../api/endpoints';
import { cn } from '../lib/utils';

interface Tenant {
  tenant_id: string;
  name: string;
  slug: string;
}

interface TenantSelectorProps {
  value: string;
  onChange: (tenant: Tenant) => void;
  className?: string;
  placeholder?: string;
  showIcon?: boolean;
  disabled?: boolean;
  onAddOption?: () => void;
}

export function TenantSelector({ 
  value, 
  onChange, 
  className, 
  placeholder = "Select Organization...", 
  showIcon = true,
  disabled = false,
  onAddOption
}: TenantSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedTenant, setSelectedTenant] = useState<Tenant | null>(null);

  useEffect(() => {
    const fetchTenants = async () => {
      setIsLoading(true);
      try {
        const res = await TenantAPI.listPublic();
        if (Array.isArray(res.data)) {
          setTenants(res.data);
          const found = res.data.find((t: Tenant) => t.tenant_id === value);
          if (found) setSelectedTenant(found);
        }
      } catch (err) {
        console.error('Failed to fetch tenants:', err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchTenants();
  }, [value]);

  const filtered = tenants.filter(t => 
    t.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    t.slug.toLowerCase().includes(searchTerm.toLowerCase()) ||
    t.tenant_id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className={cn("relative", className)}>
      <button
        type="button"
        disabled={disabled || isLoading}
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "w-full px-6 py-3.5 bg-slate-50 border border-warm-border rounded-2xl text-sm flex items-center justify-between focus:outline-none focus:border-brand-600 focus:bg-white transition-all shadow-sm",
          isOpen && "border-brand-600 bg-white ring-2 ring-brand-400/10",
          disabled && "cursor-not-allowed opacity-80"
        )}
      >
        <div className="flex items-center gap-3 overflow-hidden">
          {showIcon && <Building2 className="w-4 h-4 text-brand-500 flex-shrink-0" />}
          <span className={cn("truncate font-medium", !selectedTenant && "text-slate-400")}>
            {selectedTenant ? `${selectedTenant.name} (${selectedTenant.slug})` : placeholder}
          </span>
        </div>
        {isLoading ? (
          <Loader2 className="w-4 h-4 text-brand-400 animate-spin" />
        ) : (
          <ChevronDown className={cn("w-4 h-4 text-slate-400 transition-transform", isOpen && "rotate-180")} />
        )}
      </button>

      {isOpen && (
        <div className="absolute z-50 mt-2 w-full bg-white border border-warm-border rounded-2xl shadow-xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
          <div className="p-3 border-b border-warm-border bg-slate-50/50">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                autoFocus
                type="text"
                placeholder="Search organizations..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-9 pr-4 py-2 bg-white border border-warm-border rounded-xl text-xs focus:outline-none focus:border-brand-600 transition-all"
              />
            </div>
          </div>
          <div className="max-h-60 overflow-y-auto p-1 custom-scrollbar">
            {filtered.length === 0 ? (
              <div className="py-8 text-center text-slate-400 text-xs italic">
                No organizations found
              </div>
            ) : (
              filtered.map((tenant) => (
                <button
                  key={tenant.tenant_id}
                  type="button"
                  onClick={() => {
                    onChange(tenant);
                    setSelectedTenant(tenant);
                    setIsOpen(false);
                    setSearchTerm('');
                  }}
                  className={cn(
                    "w-full flex items-center justify-between px-4 py-3 rounded-xl text-left transition-colors group",
                    value === tenant.tenant_id ? "bg-brand-50 text-brand-700" : "hover:bg-slate-50"
                  )}
                >
                  <div className="flex flex-col">
                    <span className="text-sm font-bold">{tenant.name}</span>
                    <span className="text-[10px] text-slate-400 font-mono flex items-center gap-1">
                      {tenant.slug} • {tenant.tenant_id.slice(0, 8)}...
                    </span>
                  </div>
                  {value === tenant.tenant_id && <Check className="w-4 h-4 text-brand-600" />}
                </button>
              ))
            )}
            {onAddOption && (
              <button
                type="button"
                onClick={() => {
                  setIsOpen(false);
                  onAddOption();
                }}
                className="w-full mt-2 px-4 py-3 text-left text-sm text-brand-600 font-bold hover:bg-brand-50 border-t border-slate-100 flex items-center gap-2 transition-colors rounded-b-2xl"
              >
                <Plus className="w-4 h-4" /> Add New Organization...
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

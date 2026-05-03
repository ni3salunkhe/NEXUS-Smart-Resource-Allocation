import React from 'react';
import { User, Bell, Shield, Globe, Database, Cpu } from 'lucide-react';

export function SettingsPage() {
  return (
    <div className="flex flex-col h-full overflow-y-auto pb-10">
      <div className="mb-6">
        <h2 className="text-2xl font-headline font-semibold text-brand-900">Platform Settings</h2>
        <p className="text-sm text-gray-500">Manage your profile, organization defaults, and system parameters.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        
        {/* Profile Card */}
        <div className="bg-white p-6 rounded-3xl border border-warm-border shadow-sm flex flex-col">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-brand-50 rounded-xl text-brand-600">
              <User className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-brand-900">User Profile</h3>
          </div>
          <div className="space-y-4">
            <div className="flex flex-col">
              <label className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Display Name</label>
              <input type="text" defaultValue="Alex Chen" className="bg-slate-50 border border-warm-border rounded-xl px-4 py-2 text-sm focus:outline-none focus:border-brand-400" />
            </div>
            <div className="flex flex-col">
              <label className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Role</label>
              <input type="text" readOnly defaultValue="Operations Coordinator" className="bg-slate-100 border border-warm-border rounded-xl px-4 py-2 text-sm text-gray-500 cursor-not-allowed" />
            </div>
          </div>
          <button className="mt-8 bg-brand-600 text-white font-bold py-2.5 rounded-xl text-sm shadow-lg shadow-brand-100 hover:bg-brand-700 transition-colors">
            Save Changes
          </button>
        </div>

        {/* Notifications Card */}
        <div className="bg-white p-6 rounded-3xl border border-warm-border shadow-sm flex flex-col">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-urgency-high/10 rounded-xl text-urgency-high">
              <Bell className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-brand-900">Alert Preferences</h3>
          </div>
          <div className="space-y-4 flex-1">
            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-2xl border border-slate-100">
              <span className="text-sm text-slate-700 font-medium">Critical Need Alerts</span>
              <div className="w-10 h-5 bg-brand-600 rounded-full relative cursor-pointer">
                <div className="absolute right-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow-sm"></div>
              </div>
            </div>
            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-2xl border border-slate-100">
              <span className="text-sm text-slate-700 font-medium">Volunteer Status Upd.</span>
              <div className="w-10 h-5 bg-slate-200 rounded-full relative cursor-pointer">
                <div className="absolute left-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow-sm"></div>
              </div>
            </div>
            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-2xl border border-slate-100">
              <span className="text-sm text-slate-700 font-medium">Auto-dispatch Rec.</span>
              <div className="w-10 h-5 bg-brand-600 rounded-full relative cursor-pointer">
                <div className="absolute right-0.5 top-0.5 w-4 h-4 bg-white rounded-full shadow-sm"></div>
              </div>
            </div>
          </div>
        </div>

        {/* Security / Auth Card */}
        <div className="bg-slate-900 p-6 rounded-3xl text-white shadow-lg flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-white/10 rounded-xl">
                <Shield className="w-5 h-5 text-white" />
              </div>
              <h3 className="font-bold">Security</h3>
            </div>
            <p className="text-sm text-slate-400 leading-relaxed mb-6">
              Multi-factor authentication is active. Last password change was 42 days ago.
            </p>
          </div>
          <button className="w-full bg-white text-slate-900 font-bold py-2.5 rounded-xl text-sm hover:bg-slate-100 transition-colors">
            Update Credentials
          </button>
        </div>

        {/* Platform Status Card */}
        <div className="bg-white p-6 rounded-3xl border border-warm-border shadow-sm">
           <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-category-water/10 rounded-xl text-category-water">
              <Cpu className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-brand-900">System Health</h3>
          </div>
          <div className="grid grid-cols-2 gap-3">
             <div className="bg-slate-50 p-3 rounded-2xl border border-slate-100 text-center">
                <p className="text-[10px] font-bold text-gray-400 uppercase">Latency</p>
                <p className="text-xl font-bold text-slate-900">12ms</p>
             </div>
             <div className="bg-slate-50 p-3 rounded-2xl border border-slate-100 text-center">
                <p className="text-[10px] font-bold text-gray-400 uppercase">Uptime</p>
                <p className="text-xl font-bold text-slate-900">99.9%</p>
             </div>
             <div className="bg-slate-50 p-3 rounded-2xl border border-slate-100 text-center col-span-2">
                <p className="text-[10px] font-bold text-gray-400 uppercase">Database Instance</p>
                <p className="text-sm font-bold text-slate-700">FIRE_ENT_DB_PRIMARY</p>
             </div>
          </div>
        </div>

        {/* Language & Regional */}
        <div className="bg-amber-50 p-6 rounded-3xl border border-amber-100 flex flex-col justify-between">
           <div className="flex items-center gap-3">
            <div className="p-2 bg-amber-200 rounded-xl text-amber-800">
              <Globe className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-amber-900">Regional</h3>
          </div>
          <div className="mt-4 space-y-3">
            <p className="text-sm text-amber-800 font-medium">Default Zone: <span className="font-bold">Ward 4 / Sector B</span></p>
            <div className="flex gap-2">
               <span className="px-3 py-1 bg-amber-200 text-amber-900 text-xs font-bold rounded-full">English</span>
               <span className="px-3 py-1 bg-white text-amber-700 text-xs font-bold rounded-full border border-amber-100 cursor-pointer hover:bg-amber-100">Swahili</span>
               <span className="px-3 py-1 bg-white text-amber-700 text-xs font-bold rounded-full border border-amber-100 cursor-pointer hover:bg-amber-100">Hindi</span>
            </div>
          </div>
        </div>

        {/* Export Data */}
        <div className="bg-emerald-50 p-6 rounded-3xl border border-emerald-100 flex flex-col justify-between">
           <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-200 rounded-xl text-emerald-800">
              <Database className="w-5 h-5" />
            </div>
            <h3 className="font-bold text-emerald-900">Operations Data</h3>
          </div>
          <p className="text-xs text-emerald-700 mt-2">Export active operations logs for external auditing requirements.</p>
          <button className="mt-4 w-full bg-emerald-600 text-white font-bold py-2 rounded-xl text-xs hover:bg-emerald-700 transition-colors">
            Download CSV / JSON
          </button>
        </div>

      </div>
    </div>
  );
}

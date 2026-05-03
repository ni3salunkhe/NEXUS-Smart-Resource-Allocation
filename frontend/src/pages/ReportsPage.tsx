import React from 'react';
import { 
  FileText, 
  Download, 
  Clock, 
  Filter, 
  Calendar, 
  CheckCircle,
  FileSpreadsheet,
  FileJson,
  TrendingUp,
  Map as MapIcon,
  ArrowRight
} from 'lucide-react';
import { cn } from '../lib/utils';

const RECENT_REPORTS = [
  { id: 'REP-001', name: 'Ward 4 Operations Summary', date: '2026-04-21 08:00', size: '2.4 MB', type: 'PDF' },
  { id: 'REP-002', name: 'Volunteer Impact Audit (Q1)', date: '2026-04-20 14:30', size: '4.1 MB', type: 'XLSX' },
  { id: 'REP-003', name: 'Household Vulnerability Index', date: '2026-04-19 11:15', size: '1.2 MB', type: 'JSON' },
];

export function ReportsPage() {
  return (
    <div className="flex flex-col h-full overflow-y-auto pb-10">
      <div className="mb-6 flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-headline font-semibold text-brand-900">Reports & Analytics</h2>
          <p className="text-sm text-gray-500">Generate operational insights and export data for regulatory auditing.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        {/* Report Types Grid */}
        <div className="lg:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-4 text-white">
           <div className="bg-brand-900 p-6 rounded-[32px] flex flex-col justify-between group cursor-pointer transition-all hover:scale-[0.98]">
              <div>
                <div className="p-3 bg-brand-800 rounded-2xl w-fit mb-4">
                  <FileText className="w-6 h-6 text-brand-300" />
                </div>
                <h3 className="text-xl font-bold">Operational Status</h3>
                <p className="text-sm text-brand-200/70 mt-2">Comprehensive summary of needs, tasks, and resolution rates per sector.</p>
              </div>
              <button className="mt-6 flex items-center justify-between bg-brand-800 px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-widest hover:bg-brand-700 transition-colors">
                Generate Report <Download className="w-4 h-4 ml-2" />
              </button>
           </div>

           <div className="bg-indigo-600 p-6 rounded-[32px] flex flex-col justify-between group cursor-pointer transition-all hover:scale-[0.98]">
              <div>
                <div className="p-3 bg-indigo-500 rounded-2xl w-fit mb-4">
                  <TrendingUp className="w-6 h-6 text-indigo-200" />
                </div>
                <h3 className="text-xl font-bold">Volunteer Performance</h3>
                <p className="text-sm text-indigo-200/70 mt-2">Metrics on deployment hours, mission success, and skill distribution.</p>
              </div>
              <button className="mt-6 flex items-center justify-between bg-indigo-500 px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-widest hover:bg-indigo-400 transition-colors">
                Market Analytics <Download className="w-4 h-4 ml-2" />
              </button>
           </div>

           <div className="bg-slate-800 p-6 rounded-[32px] flex flex-col justify-between group cursor-pointer transition-all hover:scale-[0.98]">
              <div>
                <div className="p-3 bg-slate-700 rounded-2xl w-fit mb-4">
                  <FileSpreadsheet className="w-6 h-6 text-slate-300" />
                </div>
                <h3 className="text-xl font-bold">Resource Allocation</h3>
                <p className="text-sm text-slate-400 mt-2">Material distribution logs and inventory tracking across hubs.</p>
              </div>
              <button className="mt-6 flex items-center justify-between bg-slate-700 px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-widest hover:bg-slate-600 transition-colors">
                Export Data <Download className="w-4 h-4 ml-2" />
              </button>
           </div>

           <div className="bg-emerald-600 p-6 rounded-[32px] flex flex-col justify-between group cursor-pointer transition-all hover:scale-[0.98]">
              <div>
                <div className="p-3 bg-emerald-500 rounded-2xl w-fit mb-4">
                  <MapIcon className="w-6 h-6 text-emerald-200" />
                </div>
                <h3 className="text-xl font-bold">Geospatial Insights</h3>
                <p className="text-sm text-emerald-200/70 mt-2">Density maps and trend analysis over time for specific wards.</p>
              </div>
              <button className="mt-6 flex items-center justify-between bg-emerald-500 px-4 py-2 rounded-xl text-xs font-bold uppercase tracking-widest hover:bg-emerald-400 transition-colors">
                View Maps <ArrowRight className="w-4 h-4 ml-2" />
              </button>
           </div>
        </div>

        {/* Recent Exports Panel */}
        <div className="bg-white p-8 rounded-[32px] border border-warm-border shadow-sm flex flex-col h-full">
           <div className="flex items-center gap-2 mb-6">
              <Clock className="w-5 h-5 text-brand-600" />
              <h3 className="font-bold text-brand-900 text-lg">Recent Exports</h3>
           </div>
           <div className="flex-1 space-y-4">
              {RECENT_REPORTS.map(report => (
                <div key={report.id} className="p-4 bg-slate-50 border border-warm-border rounded-2xl group hover:border-brand-400 transition-all cursor-pointer">
                  <div className="flex justify-between items-start mb-2">
                     <span className={cn(
                       "text-[10px] font-bold px-1.5 py-0.5 rounded",
                       report.type === 'PDF' ? 'bg-red-100 text-red-700' : report.type === 'XLSX' ? 'bg-green-100 text-green-700' : 'bg-brand-100 text-brand-700'
                     )}>
                       {report.type}
                     </span>
                     <span className="text-[10px] font-mono text-slate-400 uppercase tracking-widest">{report.size}</span>
                  </div>
                  <h4 className="text-sm font-bold text-slate-900 mb-1 leading-tight">{report.name}</h4>
                  <p className="text-[10px] text-slate-400 font-medium">{report.date}</p>
                </div>
              ))}
              <button className="w-full py-3 bg-slate-900 text-white rounded-2xl text-xs font-bold uppercase tracking-widest hover:bg-slate-800 transition-all mt-4 border border-slate-700 shadow-xl shadow-slate-100">
                View Audit History
              </button>
           </div>
        </div>
      </div>

      {/* Advanced Filters Bento Row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
         <div className="bg-white p-6 rounded-3xl border border-warm-border shadow-sm col-span-1 md:col-span-3">
             <div className="flex items-center gap-2 mb-4">
                <Filter className="w-4 h-4 text-brand-600" />
                <h3 className="font-bold text-brand-900">Custom Export Parameters</h3>
             </div>
             <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                   <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1 block">Date Range</label>
                   <div className="bg-slate-50 border border-warm-border rounded-xl px-4 py-2 text-sm flex items-center justify-between cursor-pointer">
                      <span>Last 7 Days</span>
                      <Calendar className="w-4 h-4 text-slate-400" />
                   </div>
                </div>
                <div>
                   <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1 block">Primary Dimension</label>
                   <select className="w-full bg-slate-50 border border-warm-border rounded-xl px-4 py-2 text-sm outline-none">
                      <option>By Ward</option>
                      <option>By Category</option>
                      <option>By Volunteer</option>
                   </select>
                </div>
                <div>
                   <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1 block">Data Format</label>
                   <div className="flex bg-slate-50 p-1 rounded-xl border border-warm-border">
                      <button className="flex-1 bg-white shadow-sm py-1.5 text-xs font-bold rounded-lg text-brand-600">PDF</button>
                      <button className="flex-1 py-1.5 text-xs font-bold rounded-lg text-slate-400">CSV</button>
                      <button className="flex-1 py-1.5 text-xs font-bold rounded-lg text-slate-400">JSON</button>
                   </div>
                </div>
             </div>
         </div>
         <div className="bg-slate-900 p-8 rounded-3xl text-white flex flex-col justify-center items-center shadow-2xl relative overflow-hidden group">
            <div className="absolute top-[-10px] right-[-10px] w-20 h-20 bg-brand-600 rounded-full blur-3xl opacity-40 group-hover:opacity-60 transition-opacity"></div>
            <p className="text-[10px] font-bold text-brand-400 uppercase tracking-widest mb-2">Automate</p>
            <h4 className="text-xl font-bold mb-4 text-center leading-tight">Schedule Weekly Summaries</h4>
            <button className="bg-white text-slate-900 px-6 py-2 rounded-xl text-xs font-bold hover:bg-brand-50 transition-colors">
              Set Schedule
            </button>
         </div>
      </div>
    </div>
  );
}

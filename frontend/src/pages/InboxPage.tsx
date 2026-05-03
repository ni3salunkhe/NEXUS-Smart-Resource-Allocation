import React, { useState } from 'react';
import { 
  Search, 
  Send, 
  User, 
  Phone, 
  Video, 
  MoreHorizontal,
  Circle,
  Hash,
  MessageSquare
} from 'lucide-react';
import { cn } from '../lib/utils';

const CONTACTS = [
  { id: 'v-01', name: 'Priya Sharma', role: 'Volunteer', online: true, lastMsg: 'Need more water at Sector 2', time: '2m' },
  { id: 'v-02', name: 'Rahul Desai', role: 'Field Worker', online: true, lastMsg: 'Household HH-88219 verified', time: '15m' },
  { id: 'c-01', name: 'General Hub', role: 'Channel', online: false, lastMsg: 'Alex: Check the map updates', time: '1h' },
  { id: 'v-03', name: 'Dr. Mehta', role: 'Medical Team', online: false, lastMsg: 'Deployment confirmed for 14:00', time: '2h' },
];

export function InboxPage() {
  const [selectedContact, setSelectedContact] = useState(CONTACTS[0]);
  const [message, setMessage] = useState('');

  return (
    <div className="flex h-full bg-white rounded-[32px] overflow-hidden border border-warm-border shadow-sm">
      {/* Sidebar */}
      <div className="w-80 border-r border-warm-border flex flex-col bg-slate-50/30">
        <div className="p-6 border-b border-warm-border">
          <h2 className="text-xl font-bold text-slate-900 mb-4 tracking-tight">Communications</h2>
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input 
              type="text" 
              placeholder="Search conversations..." 
              className="w-full pl-9 pr-4 py-2 bg-white border border-warm-border rounded-xl text-sm focus:outline-none focus:border-brand-400"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto py-2">
          {CONTACTS.map((contact) => (
            <div 
              key={contact.id}
              onClick={() => setSelectedContact(contact)}
              className={cn(
                "px-4 py-3 mx-2 rounded-2xl cursor-pointer transition-all flex items-center gap-3",
                selectedContact.id === contact.id ? "bg-white shadow-sm border border-warm-border" : "hover:bg-slate-100"
              )}
            >
              <div className="relative">
                <div className="w-10 h-10 rounded-full bg-brand-100 flex items-center justify-center text-brand-600 font-bold border border-brand-200">
                  {contact.role === 'Channel' ? <Hash className="w-5 h-5" /> : contact.name.charAt(0)}
                </div>
                {contact.online && (
                  <div className="absolute bottom-0 right-0 w-3 h-3 bg-emerald-500 border-2 border-white rounded-full"></div>
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex justify-between items-center mb-0.5">
                  <h4 className="text-sm font-bold text-slate-900 truncate">{contact.name}</h4>
                  <span className="text-[10px] font-medium text-slate-400">{contact.time}</span>
                </div>
                <p className="text-xs text-slate-500 truncate">{contact.lastMsg}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 flex flex-col bg-white">
        <div className="h-16 px-6 border-b border-warm-border flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-brand-50 flex items-center justify-center text-brand-600 font-bold text-xs">
              {selectedContact.name.charAt(0)}
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900 leading-none">{selectedContact.name}</h3>
              <span className="text-[10px] text-slate-400 font-medium">{selectedContact.role} • Active now</span>
            </div>
          </div>
          <div className="flex items-center gap-4 text-slate-400">
            <button className="hover:text-brand-600 transition-colors"><Phone className="w-4 h-4" /></button>
            <button className="hover:text-brand-600 transition-colors"><Video className="w-4 h-4" /></button>
            <button className="hover:text-brand-600 transition-colors"><MoreHorizontal className="w-4 h-4" /></button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-50/20">
          <div className="flex flex-col items-center py-4">
             <span className="text-[10px] font-bold text-slate-300 uppercase tracking-widest px-4 py-1 border border-slate-100 rounded-full">Today</span>
          </div>

          <div className="flex gap-3 max-w-[70%]">
             <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center text-brand-600 font-bold shrink-0 text-xs">P</div>
             <div className="bg-white p-4 rounded-2xl rounded-tl-none border border-warm-border shadow-sm">
                <p className="text-sm text-slate-700 leading-relaxed">
                  We have reached the household in Sector 2. There is a specific need for medical supplies (insulin) that wasn't in the initial report. Updating HH-88219 now.
                </p>
                <span className="text-[10px] text-slate-400 mt-2 block">10:42 AM</span>
             </div>
          </div>

          <div className="flex flex-row-reverse gap-3 max-w-[70%] ml-auto">
             <div className="w-8 h-8 rounded-full bg-slate-900 flex items-center justify-center text-white font-bold shrink-0 text-xs text-center">AC</div>
             <div className="bg-brand-600 p-4 rounded-2xl rounded-tr-none text-white shadow-lg shadow-brand-100">
                <p className="text-sm leading-relaxed">
                  Copy that, Priya. Initiating medical dispatch from the central hub. Stand by for ETA.
                </p>
                <span className="text-[10px] text-brand-200 mt-2 block text-right">10:43 AM</span>
             </div>
          </div>
        </div>

        <div className="p-6 border-t border-warm-border">
          <div className="relative">
            <input 
              type="text" 
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder={`Message ${selectedContact.name}...`} 
              className="w-full pl-4 pr-12 py-3 bg-slate-50 border border-warm-border rounded-2xl text-sm focus:outline-none focus:border-brand-400"
            />
            <button className="absolute right-2 top-1/2 -translate-y-1/2 w-8 h-8 bg-brand-600 text-white rounded-xl flex items-center justify-center transition-transform hover:scale-110 active:scale-95 shadow-md shadow-brand-100">
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

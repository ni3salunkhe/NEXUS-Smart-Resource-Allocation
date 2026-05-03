import { 
  Bell, 
  Search, 
  User, 
  Home, 
  ArrowRight, 
  X, 
  Command, 
  Users, 
  ShieldAlert, 
  Zap,
  Wifi,
  WifiOff,
  CloudUpload,
  RefreshCcw
} from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../stores/auth.store';
import { useNotificationStore } from '../../stores/notification.store';
import { useUiStore } from '../../stores/ui.store';
import { useSyncStore } from '../../stores/sync.store';
import { useHouseholdStore, Household } from '../../stores/household.store';
import { filterHouseholds } from '../../lib/searchUtils';
import { useVolunteerStore, Volunteer } from '../../stores/volunteer.store';
import { NAV_ITEMS } from '../../constants/navigation';
import { hasPermission } from '../../constants/permissions';
import { cn } from '../../lib/utils';

export function Header() {
  const navigate = useNavigate();
  const { display_name, org_name, role } = useAuthStore();
  const { unread_count } = useNotificationStore();
  const { households } = useHouseholdStore();
  const { volunteers } = useVolunteerStore();
  const { openPanel, emergencyMode, toggleEmergencyMode } = useUiStore();
  const { isOnline, pendingSyncCount } = useSyncStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [showResults, setShowResults] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  const filteredNavItems = searchQuery 
    ? NAV_ITEMS.filter(item => 
        hasPermission(role as any, item.feature) && 
        item.label.toLowerCase().includes(searchQuery.toLowerCase())
      ).slice(0, 3)
    : [];

  const filteredHouseholds = searchQuery 
    ? filterHouseholds(households, searchQuery).slice(0, 4)
    : [];

  const filteredVolunteers = searchQuery
    ? volunteers.filter(v => 
        v.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        v.vol_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
        v.skills.some(s => s.toLowerCase().includes(searchQuery.toLowerCase()))
      ).slice(0, 3)
    : [];

  const totalResults = filteredNavItems.length + filteredHouseholds.length + filteredVolunteers.length;

  const searchInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
      if (e.key === 'Escape') {
        setShowResults(false);
      }
    };

    const handleClickOutside = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowResults(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const handleResultClick = (hh: Household) => {
    setSearchQuery('');
    setShowResults(false);
    openPanel('household_details', hh.hh_id);
    navigate('/households');
  };

  return (
    <header className="h-full w-full bg-white px-6 flex items-center justify-between z-50 relative">
      <div className="flex items-center gap-4 flex-1">
        <h1 className="text-xl font-headline font-semibold text-brand-900">
          {org_name || 'Nexus Response Unit'}
        </h1>
        <div className="hidden md:flex ml-4 max-w-md w-full relative" ref={searchRef}>
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input 
            ref={searchInputRef}
            type="text" 
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setShowResults(true);
            }}
            onFocus={() => searchQuery && setShowResults(true)}
            placeholder="Search Global ID, Household..." 
            className="w-full pl-9 pr-12 py-1.5 bg-slate-50 border border-warm-border rounded-xl text-sm focus:outline-none focus:border-brand-400 focus:ring-1 focus:ring-brand-400 transition-shadow"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1.5 pointer-events-none">
            {searchQuery ? (
              <button 
                onClick={(e) => { 
                  e.stopPropagation();
                  setSearchQuery(''); 
                  setShowResults(false); 
                }}
                className="pointer-events-auto text-gray-400 hover:text-brand-600"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            ) : (
              <div className="flex items-center gap-0.5 px-1.5 py-0.5 rounded border border-gray-200 bg-white shadow-sm">
                <span className="text-[10px] font-mono font-bold text-gray-400">⌘</span>
                <span className="text-[10px] font-mono font-bold text-gray-400 uppercase">K</span>
              </div>
            )}
          </div>

          {/* Search Results Dropdown */}
          {showResults && searchQuery && (
            <div className="absolute top-full left-0 w-full mt-2 bg-white border border-warm-border rounded-2xl shadow-2xl overflow-hidden z-[100] animate-in fade-in slide-in-from-top-2 duration-200">
              <div className="p-3 border-b border-warm-border bg-slate-50/50 flex justify-between items-center">
                <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Global Search Results</span>
                <span className="text-[10px] text-gray-400">Esc to close</span>
              </div>
              <div className="max-h-[420px] overflow-y-auto">
                {totalResults > 0 ? (
                  <div className="p-2 space-y-4">
                    {/* Navigation Category */}
                    {filteredNavItems.length > 0 && (
                      <div className="space-y-1">
                        <div className="px-3 py-1 flex items-center gap-2">
                          <Command className="w-3 h-3 text-brand-600" />
                          <span className="text-[10px] font-bold text-brand-600 uppercase tracking-tighter">Apps & Menus</span>
                        </div>
                        {filteredNavItems.map(item => (
                          <button
                            key={item.path}
                            onClick={() => {
                              navigate(item.path);
                              setSearchQuery('');
                              setShowResults(false);
                            }}
                            className="w-full text-left px-3 py-2 hover:bg-brand-50 rounded-lg flex items-center gap-3 group transition-colors"
                          >
                            <div className="w-7 h-7 rounded-md bg-white border border-warm-border flex items-center justify-center text-gray-400 group-hover:text-brand-600 group-hover:border-brand-200">
                              <item.icon className="w-3.5 h-3.5" />
                            </div>
                            <span className="text-sm font-medium text-brand-900">{item.label}</span>
                            <span className="ml-auto text-[10px] text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity">Open Module</span>
                          </button>
                        ))}
                      </div>
                    )}

                    {/* Households Category */}
                    {filteredHouseholds.length > 0 && (
                      <div className="space-y-1">
                        <div className="px-3 py-1 flex items-center gap-2">
                          <Home className="w-3 h-3 text-brand-600" />
                          <span className="text-[10px] font-bold text-brand-600 uppercase tracking-tighter">Households</span>
                        </div>
                        {filteredHouseholds.map(hh => (
                          <button
                            key={hh.hh_id}
                            onClick={() => handleResultClick(hh)}
                            className="w-full text-left px-3 py-2 hover:bg-brand-50 rounded-lg flex items-center gap-3 group transition-colors"
                          >
                            <div className="w-7 h-7 rounded-md bg-white border border-warm-border flex items-center justify-center text-gray-400 group-hover:text-brand-600">
                              <Home className="w-3.5 h-3.5" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <span className="text-sm font-medium text-brand-900 block truncate">{hh.hh_id}</span>
                              <span className="text-[10px] text-gray-400 truncate block">{hh.location_desc}</span>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}

                    {/* Volunteers Category */}
                    {filteredVolunteers.length > 0 && (
                      <div className="space-y-1">
                        <div className="px-3 py-1 flex items-center gap-2">
                          <Users className="w-3 h-3 text-brand-600" />
                          <span className="text-[10px] font-bold text-brand-600 uppercase tracking-tighter">Volunteers</span>
                        </div>
                        {filteredVolunteers.map(vol => (
                          <button
                            key={vol.vol_id}
                            onClick={() => {
                              navigate('/volunteers');
                              setSearchQuery('');
                              setShowResults(false);
                            }}
                            className="w-full text-left px-3 py-2 hover:bg-brand-50 rounded-lg flex items-center gap-3 group transition-colors"
                          >
                            <div className="w-7 h-7 rounded-md bg-white border border-warm-border flex items-center justify-center text-gray-400 group-hover:text-brand-600">
                              <User className="w-3.5 h-3.5" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <span className="text-sm font-medium text-brand-900 block truncate">{vol.name}</span>
                              <span className="text-[10px] text-gray-400 truncate block">{vol.vol_id} • {vol.skills[0].replace('_', ' ')}</span>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="p-8 text-center">
                    <div className="w-12 h-12 rounded-full bg-gray-50 flex items-center justify-center mx-auto mb-3">
                      <Search className="w-6 h-6 text-gray-300" />
                    </div>
                    <p className="text-sm text-brand-900 font-headline italic">No results found for "{searchQuery}"</p>
                    <p className="text-[10px] text-gray-400 mt-1 uppercase tracking-widest">Try searching by ID or location</p>
                  </div>
                )}
              </div>
              {filteredHouseholds.length > 0 && (
                <div className="p-3 bg-slate-50 border-t border-warm-border text-center">
                   <button 
                    onClick={() => {
                      navigate(`/households?search=${searchQuery}`);
                      setShowResults(false);
                    }}
                    className="text-[11px] font-bold text-brand-600 hover:text-brand-800 transition-colors uppercase tracking-widest"
                  >
                    View all household results
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      
      <div className="flex items-center gap-4">
        {/* Connection & Sync Status */}
        <div className="flex items-center gap-3 mr-2">
          {pendingSyncCount > 0 && (
            <div className="flex items-center gap-1.5 px-2 py-1 bg-brand-50 border border-brand-100 rounded-lg animate-pulse">
              <CloudUpload className="w-3.5 h-3.5 text-brand-600" />
              <span className="text-[10px] font-bold text-brand-600 uppercase tracking-tighter">
                {pendingSyncCount} Pending
              </span>
            </div>
          )}
          
          <div className={cn(
            "flex items-center gap-1.5 px-2 py-1 rounded-lg border transition-colors",
            isOnline 
              ? "bg-green-50 border-green-100 text-green-600" 
              : "bg-amber-50 border-amber-100 text-amber-600"
          )} title={isOnline ? 'Online - System Sync Active' : 'Offline - Local Storage Only'}>
            {isOnline ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
            <span className="text-[10px] font-bold uppercase tracking-tighter leading-none pt-0.5">
              {isOnline ? 'Online' : 'Offline'}
            </span>
          </div>
        </div>

        <button 
          onClick={toggleEmergencyMode}
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-bold transition-all border shadow-sm",
            emergencyMode 
              ? "bg-black text-white border-black scale-105" 
              : "bg-red-50 text-red-600 border-red-100 hover:bg-red-100"
          )}
          title={emergencyMode ? "Disable Emergency Mode" : "Enable Emergency Mode"}
        >
          <ShieldAlert className={cn("w-4 h-4", emergencyMode && "animate-pulse")} />
          {emergencyMode ? "EMERGENCY ENABLED" : "EMERGENCY MODE"}
        </button>

        <button className="relative p-2 text-gray-500 hover:text-brand-600 transition-colors rounded-full hover:bg-slate-50">
          <Bell className="w-5 h-5" />
          {unread_count > 0 && (
            <span className="absolute top-1 right-1 flex items-center justify-center w-4 h-4 text-[10px] font-bold text-white bg-urgency-critical rounded-full">
              {unread_count > 99 ? '99+' : unread_count}
            </span>
          )}
        </button>
        
        <div className="h-8 w-px bg-warm-border mx-1"></div>
        
        <div className="flex flex-col text-right">
          <span className="text-sm font-semibold text-brand-900 leading-tight">{display_name || 'Coordinator'}</span>
          <span className="text-xs text-gray-500 uppercase tracking-widest leading-tight">{role?.replace('_', ' ')}</span>
        </div>
        <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center text-brand-600 font-bold border border-brand-200">
          {display_name?.charAt(0).toUpperCase() || 'C'}
        </div>
      </div>
    </header>
  );
}

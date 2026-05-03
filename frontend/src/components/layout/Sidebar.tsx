import { NavLink } from 'react-router-dom';
import { useAuthStore } from '../../stores/auth.store';
import { useUiStore } from '../../stores/ui.store';
import { cn } from '../../lib/utils';
import { 
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';

import { hasPermission } from '../../constants/permissions';
import { NAV_ITEMS } from '../../constants/navigation';

import { RoleSwitcher } from '../auth/RoleSwitcher';

export function Sidebar() {
  const { role, clearAuth, display_name } = useAuthStore();
  const { sidebarOpen, toggleSidebar, emergencyMode } = useUiStore();

  const filteredNavItems = NAV_ITEMS.filter(item => hasPermission(role as any, item.feature));

  return (
    <aside
      className={cn(
        "bg-brand-900 text-brand-50 flex flex-col h-full transition-all duration-300 relative",
        sidebarOpen ? "w-64" : "w-16",
        emergencyMode && "bg-black text-white border-r-4 border-black border-opacity-100"
      )}
    >
      <div className="flex h-20 items-center gap-3 px-4 flex-shrink-0">
        <div className={cn(
          "w-10 h-10 bg-brand-600 rounded-xl flex items-center justify-center shadow-lg shadow-brand-900/40",
          emergencyMode && "bg-white rounded-none shadow-none"
        )}>
          <div className={cn(
            "w-5 h-5 border-2 border-white rounded-full",
            emergencyMode && "border-black bg-black"
          )}></div>
        </div>
        {sidebarOpen && <h1 className="text-xl font-bold text-white tracking-tight">NEXUS</h1>}
        {!sidebarOpen && <div className="absolute right-[-10px] top-7">
           <button
            onClick={toggleSidebar}
            className={cn(
              "bg-brand-600 rounded-full p-1 border border-brand-800 shadow-sm",
              emergencyMode && "bg-black border-white rounded-none p-2 right-[-20px]"
            )}
          >
            <ChevronRight className="w-4 h-4 text-white" />
          </button>
        </div>}
      </div>

      {sidebarOpen && (
        <button
          onClick={toggleSidebar}
          className={cn(
            "absolute top-7 right-4 text-brand-200 hover:text-white transition-colors",
            emergencyMode && "text-white font-bold underline"
          )}
        >
          {emergencyMode ? "CLOSE" : <ChevronLeft className="w-5 h-5" />}
        </button>
      )}

      <nav className="flex-1 overflow-y-auto py-4 space-y-1">
        {filteredNavItems.map((item) => {
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                cn(
                  "flex items-center px-4 py-3 mx-2 rounded-md transition-colors",
                  isActive
                    ? (emergencyMode ? "bg-white text-black font-black" : "bg-brand-600 text-white font-medium shadow-lg shadow-brand-900/30")
                    : (emergencyMode ? "text-white hover:bg-white/20" : "text-brand-200 hover:bg-brand-800 hover:text-white")
                )
              }
              title={!sidebarOpen ? item.label : undefined}
            >
              <item.icon className={cn("w-5 h-5", sidebarOpen && "mr-3", emergencyMode && "stroke-[3px]")} />
              {sidebarOpen && <span>{item.label}</span>}
            </NavLink>
          );
        })}
      </nav>

      <div className="flex flex-col gap-1 p-2 border-t border-brand-800">
        <RoleSwitcher minimized={!sidebarOpen} />
        
        {hasPermission(role as any, 'settings') && (
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              cn(
                "flex items-center px-4 py-3 mx-2 rounded-md transition-colors",
                isActive
                  ? "bg-brand-600 text-white font-medium shadow-lg shadow-brand-900/30"
                  : "text-brand-200 hover:bg-brand-800 hover:text-white"
              )
            }
          >
            <Settings className={cn("w-5 h-5", sidebarOpen && "mr-3")} />
            {sidebarOpen && <span>Settings</span>}
          </NavLink>
        )}
        <button
          onClick={clearAuth}
          className="flex items-center px-4 py-3 mx-2 rounded-md text-brand-200 hover:bg-brand-800 hover:text-white transition-colors"
        >
          <LogOut className={cn("w-5 h-5", sidebarOpen && "mr-3")} />
          {sidebarOpen && <span>Sign Out</span>}
        </button>
      </div>
    </aside>
  );
}

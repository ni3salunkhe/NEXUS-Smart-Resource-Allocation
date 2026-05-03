import { Outlet, Navigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useAuthStore } from '../../stores/auth.store';
import { useUiStore } from '../../stores/ui.store';
import { cn } from '../../lib/utils';
import { useEffect } from 'react';
import { useSocketStore } from '../../stores/socket.store';

export function AppLayout() {
  const { jwt } = useAuthStore();
  const { emergencyMode } = useUiStore();
  const { connect, disconnect } = useSocketStore();

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return (
    <div className={cn(
      "flex h-screen w-full overflow-hidden bg-slate-50 font-sans text-brand-900 p-6 gap-6 transition-all duration-300",
      emergencyMode && "emergency-mode p-0 gap-0 rounded-none bg-white"
    )}>
      <div className={cn(
        "rounded-3xl overflow-hidden shadow-xl shadow-brand-200 flex flex-col bg-brand-900 text-white shrink-0 transition-all",
        emergencyMode && "rounded-none border-r-4 border-black"
      )}>
        <Sidebar />
      </div>
      <div className="flex-1 flex flex-col min-w-0 gap-6 h-full">
        <div className={cn(
          "rounded-3xl shadow-sm border border-warm-border bg-white flex items-center justify-between h-16 shrink-0 overflow-hidden transition-all",
          emergencyMode && "rounded-none border-b-4 border-black border-t-0 border-r-0 border-l-0 h-20"
        )}>
          <Header />
        </div>
        <main className={cn(
          "flex-1 overflow-auto relative flex flex-col transition-all",
          emergencyMode && "bg-white p-4"
        )}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

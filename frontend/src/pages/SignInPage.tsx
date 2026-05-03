import React, { useState } from 'react';
import { Shield, ArrowRight, Github, Chrome, AlertCircle } from 'lucide-react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../stores/auth.store';

export function SignInPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const navigate = useNavigate();
  const { login, isLoading, error } = useAuthStore();

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    const success = await login(email, password);
    if (success) {
      navigate('/');
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6 font-sans">
      <div className="max-w-5xl w-full grid grid-cols-1 lg:grid-cols-2 gap-8 items-center">
        
        {/* Left Side: Branding/Intro */}
        <div className="hidden lg:flex flex-col">
           <div className="w-16 h-16 bg-brand-900 rounded-3xl flex items-center justify-center shadow-2xl shadow-brand-200 mb-8">
              <div className="w-8 h-8 border-4 border-white rounded-full"></div>
           </div>
           <h1 className="text-6xl font-bold text-slate-900 leading-[0.9] tracking-tighter mb-6 underline decoration-brand-600 underline-offset-8">
              NEXUS <br /> CORE
           </h1>
           <p className="text-xl text-slate-500 leading-relaxed max-w-md">
              The unified operational nervous system for high-stakes field response and resource orchestration.
           </p>
           
           <div className="grid grid-cols-2 gap-4 mt-12">
              <div className="p-6 bg-white rounded-3xl border border-warm-border shadow-sm">
                 <p className="text-3xl font-bold text-brand-900">14k+</p>
                 <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mt-1">Deployments</p>
              </div>
              <div className="p-6 bg-brand-900 rounded-3xl shadow-xl shadow-brand-100 text-white">
                 <p className="text-3xl font-bold">99.9%</p>
                 <p className="text-xs font-bold text-brand-300 uppercase tracking-widest mt-1">Reliability</p>
              </div>
           </div>
        </div>

        {/* Right Side: Auth Form */}
        <div className="bg-white p-8 md:p-12 rounded-[48px] shadow-2xl border border-warm-border relative overflow-hidden">
           {/* Animated Background Element */}
           <div className="absolute top-[-100px] right-[-100px] w-64 h-64 bg-brand-50 rounded-full blur-[100px]"></div>

           <div className="relative">
              <div className="mb-10">
                <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Security Access</h2>
                <p className="text-slate-400 mt-2 font-medium">Please enter your specialized credentials to initialize current sessions.</p>
              </div>

              {error && (
                <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-2xl flex items-center gap-3 text-sm text-red-700">
                  <AlertCircle className="w-5 h-5 flex-shrink-0" />
                  {error}
                </div>
              )}

              <form onSubmit={handleSignIn} className="space-y-6">
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2 px-1">Organizational Identity</label>
                  <input 
                    type="email" 
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@nexus.org"
                    className="w-full px-6 py-4 bg-slate-50 border border-warm-border rounded-2xl text-sm focus:outline-none focus:border-brand-600 focus:bg-white transition-all shadow-sm"
                  />
                </div>

                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2 px-1">Biometric / Passkey Secret</label>
                  <input 
                    type="password" 
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full px-6 py-4 bg-slate-50 border border-warm-border rounded-2xl text-sm focus:outline-none focus:border-brand-600 focus:bg-white transition-all shadow-sm"
                  />
                </div>

                <div className="flex items-center justify-between px-1">
                  <label className="flex items-center gap-2 cursor-pointer group">
                    <input type="checkbox" className="w-4 h-4 rounded text-brand-600 focus:ring-brand-400 accent-brand-600" />
                    <span className="text-xs font-medium text-slate-500 group-hover:text-slate-800 transition-colors">Remember identity</span>
                  </label>
                  <button type="button" className="text-xs font-bold text-brand-600 hover:text-brand-700">Lost Key?</button>
                </div>

                <button 
                  disabled={isLoading}
                  className="w-full bg-brand-900 text-white font-bold py-5 rounded-2xl shadow-xl shadow-brand-100 flex items-center justify-center gap-3 hover:bg-slate-900 transition-all active:scale-[0.98] disabled:opacity-70 disabled:cursor-not-allowed group"
                >
                  {isLoading ? 'Decrypting...' : 'Initialize Session'}
                  {!isLoading && <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />}
                </button>
              </form>

              <div className="mt-10 pt-8 border-t border-slate-100">
                <p className="text-center text-[10px] font-bold text-slate-300 uppercase tracking-[0.2em] mb-6">Or Authenticate With</p>
                <div className="grid grid-cols-2 gap-4">
                  <button className="flex items-center justify-center gap-2 py-3 border border-warm-border rounded-2xl hover:bg-slate-50 transition-colors">
                    <Chrome className="w-4 h-4 text-slate-600" />
                    <span className="text-xs font-bold text-slate-700">Google SSO</span>
                  </button>
                  <button className="flex items-center justify-center gap-2 py-3 border border-warm-border rounded-2xl hover:bg-slate-50 transition-colors">
                    <Github className="w-4 h-4 text-slate-800" />
                    <span className="text-xs font-bold text-slate-700">Enterprise ID</span>
                  </button>
                </div>
              </div>

               <div className="mt-6 text-center">
                 <p className="text-sm text-slate-500">
                   Don't have an account?{' '}
                   <Link to="/auth/signup" className="text-brand-600 font-bold hover:text-brand-800 transition-colors">
                     Create Account
                   </Link>
                 </p>
               </div>
           </div>
        </div>

      </div>
    </div>
  );
}

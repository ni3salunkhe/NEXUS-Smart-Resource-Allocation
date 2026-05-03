import React, { useState } from 'react';
import { Shield, ArrowRight, UserPlus, Eye, EyeOff, CheckCircle, AlertCircle } from 'lucide-react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../stores/auth.store';
import { AuthAPI, TenantAPI } from '../api/endpoints';
import { toast } from 'react-hot-toast';
import { TenantSelector } from '../components/TenantSelector';

export function SignUpPage() {
  const navigate = useNavigate();
  const { setAuth } = useAuthStore();

  const [form, setForm] = useState({
    display_name: '',
    email: '',
    password: '',
    confirm_password: '',
    tenant_id: '',
    role: 'volunteer' as 'volunteer' | 'field_worker' | 'coordinator',
  });
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const updateField = (field: string, value: string) =>
    setForm(prev => ({ ...prev, [field]: value }));

  const passwordStrength = (() => {
    const p = form.password;
    if (!p) return { score: 0, label: '', color: '' };
    let score = 0;
    if (p.length >= 8) score++;
    if (/[A-Z]/.test(p)) score++;
    if (/[0-9]/.test(p)) score++;
    if (/[^A-Za-z0-9]/.test(p)) score++;
    const labels = ['', 'Weak', 'Fair', 'Strong', 'Very Strong'];
    const colors = ['', 'bg-red-500', 'bg-amber-500', 'bg-blue-500', 'bg-green-500'];
    return { score, label: labels[score], color: colors[score] };
  })();

  const canSubmit =
    form.display_name.length >= 2 &&
    form.email.includes('@') &&
    form.password.length >= 8 &&
    form.password === form.confirm_password &&
    form.tenant_id.length > 0;

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    setIsLoading(true);
    setError(null);

    try {
      const res = await AuthAPI.signup({
        email: form.email,
        password: form.password,
        display_name: form.display_name,
        tenant_id: form.tenant_id,
        role: form.role,
      });

      const data = res.data;
      setAuth({
        jwt: data.jwt ?? data.access_token ?? '',
        user_id: data.user_id,
        display_name: data.display_name,
        role: data.role,
        tenant_id: data.tenant_id,
      });
      toast.success(`Welcome, ${data.display_name}!`, { icon: '🎉', duration: 3000 });
      navigate('/');
    } catch (err: any) {
      let msg = 'Registration failed';
      if (err?.response?.data?.detail) {
        if (Array.isArray(err.response.data.detail)) {
          msg = err.response.data.detail[0].msg;
        } else {
          msg = err.response.data.detail;
        }
      }
      setError(msg);
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6 font-sans">
      <div className="max-w-5xl w-full grid grid-cols-1 lg:grid-cols-2 gap-8 items-center">

        {/* Left Side: Branding */}
        <div className="hidden lg:flex flex-col">
          <div className="w-16 h-16 bg-brand-600 rounded-3xl flex items-center justify-center shadow-2xl shadow-brand-200 mb-8">
            <UserPlus className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-6xl font-bold text-slate-900 leading-[0.9] tracking-tighter mb-6 underline decoration-brand-600 underline-offset-8">
            JOIN <br />NEXUS
          </h1>
          <p className="text-xl text-slate-500 leading-relaxed max-w-md">
            Create your operational identity to join the humanitarian response network and begin coordinating field deployments.
          </p>

          <div className="grid grid-cols-3 gap-4 mt-12">
            <div className="p-5 bg-white rounded-3xl border border-warm-border shadow-sm text-center">
              <p className="text-2xl font-bold text-brand-900">3</p>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">Services</p>
            </div>
            <div className="p-5 bg-brand-600 rounded-3xl shadow-xl shadow-brand-100 text-white text-center">
              <p className="text-2xl font-bold">E2E</p>
              <p className="text-[10px] font-bold text-brand-200 uppercase tracking-widest mt-1">Encrypted</p>
            </div>
            <div className="p-5 bg-slate-900 rounded-3xl shadow-xl text-white text-center">
              <p className="text-2xl font-bold">RLS</p>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">Isolated</p>
            </div>
          </div>
        </div>

        {/* Right Side: Registration Form */}
        <div className="bg-white p-8 md:p-10 rounded-[48px] shadow-2xl border border-warm-border relative overflow-hidden">
          <div className="absolute top-[-100px] right-[-100px] w-64 h-64 bg-brand-50 rounded-full blur-[100px]"></div>
          <div className="absolute bottom-[-80px] left-[-80px] w-48 h-48 bg-indigo-50 rounded-full blur-[80px]"></div>

          <div className="relative">
            <div className="mb-8">
              <h2 className="text-3xl font-bold text-slate-900 tracking-tight">Create Account</h2>
              <p className="text-slate-400 mt-2 font-medium">Register to access the NEXUS operational platform.</p>
            </div>

            {error && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-2xl flex items-center gap-3 text-sm text-red-700">
                <AlertCircle className="w-5 h-5 flex-shrink-0" />
                {error}
              </div>
            )}

            <form onSubmit={handleSignUp} className="space-y-5">
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2 px-1">Full Name</label>
                <input
                  type="text"
                  required
                  value={form.display_name}
                  onChange={e => updateField('display_name', e.target.value)}
                  placeholder="Alex Chen"
                  className="w-full px-6 py-3.5 bg-slate-50 border border-warm-border rounded-2xl text-sm focus:outline-none focus:border-brand-600 focus:bg-white transition-all shadow-sm"
                />
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2 px-1">Email Address</label>
                <input
                  type="email"
                  required
                  value={form.email}
                  onChange={e => updateField('email', e.target.value)}
                  placeholder="name@nexus.org"
                  className="w-full px-6 py-3.5 bg-slate-50 border border-warm-border rounded-2xl text-sm focus:outline-none focus:border-brand-600 focus:bg-white transition-all shadow-sm"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2 px-1">Organization</label>
                  <TenantSelector
                    value={form.tenant_id}
                    onChange={val => updateField('tenant_id', val)}
                    placeholder="Search NGO..."
                  />
                </div>
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2 px-1">Role</label>
                  <select
                    value={form.role}
                    onChange={e => updateField('role', e.target.value)}
                    className="w-full px-5 py-3.5 bg-slate-50 border border-warm-border rounded-2xl text-sm focus:outline-none focus:border-brand-600 focus:bg-white transition-all shadow-sm"
                  >
                    <option value="volunteer">Volunteer</option>
                    <option value="field_worker">Field Worker</option>
                    <option value="coordinator">Coordinator</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2 px-1">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    minLength={8}
                    value={form.password}
                    onChange={e => updateField('password', e.target.value)}
                    placeholder="Min 8 characters"
                    className="w-full px-6 py-3.5 bg-slate-50 border border-warm-border rounded-2xl text-sm focus:outline-none focus:border-brand-600 focus:bg-white transition-all shadow-sm pr-12"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                {form.password && (
                  <div className="mt-2 flex items-center gap-2">
                    <div className="flex-1 flex gap-1">
                      {[1, 2, 3, 4].map(i => (
                        <div
                          key={i}
                          className={`h-1 flex-1 rounded-full transition-colors ${i <= passwordStrength.score ? passwordStrength.color : 'bg-slate-200'}`}
                        />
                      ))}
                    </div>
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">{passwordStrength.label}</span>
                  </div>
                )}
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-2 px-1">Confirm Password</label>
                <input
                  type="password"
                  required
                  value={form.confirm_password}
                  onChange={e => updateField('confirm_password', e.target.value)}
                  placeholder="Re-enter password"
                  className={`w-full px-6 py-3.5 bg-slate-50 border rounded-2xl text-sm focus:outline-none transition-all shadow-sm ${
                    form.confirm_password && form.confirm_password !== form.password
                      ? 'border-red-300 focus:border-red-500'
                      : 'border-warm-border focus:border-brand-600'
                  }`}
                />
                {form.confirm_password && form.confirm_password === form.password && (
                  <div className="mt-1 flex items-center gap-1 text-green-600">
                    <CheckCircle className="w-3 h-3" />
                    <span className="text-[10px] font-bold uppercase tracking-wider">Match</span>
                  </div>
                )}
              </div>

              <button
                type="submit"
                disabled={!canSubmit || isLoading}
                className="w-full bg-brand-600 text-white font-bold py-4 rounded-2xl shadow-xl shadow-brand-100 flex items-center justify-center gap-3 hover:bg-brand-800 transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed group mt-2"
              >
                {isLoading ? (
                  <span className="flex items-center gap-2">
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Creating Account...
                  </span>
                ) : (
                  <>
                    Create Account
                    <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
                  </>
                )}
              </button>
            </form>

            <div className="mt-8 pt-6 border-t border-slate-100 text-center">
              <p className="text-sm text-slate-500">
                Already have an account?{' '}
                <Link to="/auth/signin" className="text-brand-600 font-bold hover:text-brand-800 transition-colors">
                  Sign In
                </Link>
              </p>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

import React, { useState } from 'react';
import { Shield, Key, AlertCircle, ArrowRight, Lock, User, UserPlus, Sparkles, CheckCircle2, X } from 'lucide-react';
import { login, registerUser } from '../api';

export default function LoginModal({ isOpen, onClose, onLoginSuccess, systemSettings, isDemoAllowed = false }) {
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [role, setRole] = useState('reviewer'); // 'reviewer' | 'auditor' | 'admin'
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const allowRegistration = systemSettings?.allow_self_registration !== false;

  if (!isOpen) return null;

  async function handleSubmit(e) {
    if (e) e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      if (mode === 'login') {
        const data = await login(username, password);
        onLoginSuccess(data.user, data.role);
        onClose();
      } else {
        if (!allowRegistration) {
          throw new Error('Self-registration is disabled in this environment. Contact an administrator.');
        }
        const data = await registerUser({
          username,
          password,
          full_name: fullName || username,
          role,
        });
        setSuccess('Account created successfully! Logging you in...');
        setTimeout(() => {
          onLoginSuccess(data.user, data.role);
          onClose();
        }, 600);
      }
    } catch (err) {
      setError(err.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  }

  async function handleQuickLogin(userToLogin, passToLogin) {
    if (!isDemoAllowed) {
      setError('Demo logins are disabled in this environment.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await login(userToLogin, passToLogin);
      onLoginSuccess(data.user, data.role);
      onClose();
    } catch (err) {
      setError(err.message || 'Quick login failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  }

  function handleFillDemo(demoRole = 'reviewer') {
    if (!isDemoAllowed) return;
    if (demoRole === 'reviewer') {
      setUsername('reviewer');
      setPassword('password123');
    } else if (demoRole === 'admin') {
      setUsername('admin');
      setPassword('admin_secret_2026');
    }
    setError(null);
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content card-sheen p-6 sm:p-8 relative max-w-md border border-slate-700/80 shadow-2xl">
        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-400 hover:text-white p-1.5 rounded-lg hover:bg-slate-800/80 transition-colors cursor-pointer"
          title="Close modal"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Header */}
        <div className="text-center mb-6">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-cyan-400 p-[1.5px] mx-auto mb-3.5 shadow-lg shadow-indigo-500/25">
            <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center text-indigo-400">
              <Shield className="w-6 h-6" />
            </div>
          </div>
          <h3 className="font-heading text-2xl font-bold text-white mb-1.5 tracking-tight">
            {mode === 'login' ? 'Merchant Console Access' : 'Create Merchant Account'}
          </h3>
          <p className="text-xs text-slate-400">
            {mode === 'login'
              ? 'Sign in to access automated dispute defense and approval tokens.'
              : 'Register a new reviewer or compliance auditor for your organization.'}
          </p>
        </div>

        {/* Quick Demo Access for Evaluators */}
        {isDemoAllowed && mode === 'login' && (
          <div className="mb-6 p-4 rounded-2xl bg-gradient-to-br from-indigo-950/70 via-slate-900 to-slate-950 border border-indigo-500/35 shadow-lg shadow-indigo-500/5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-cyan-400" />
                <span className="text-xs sm:text-sm font-bold text-indigo-300">Razorpay Evaluator 1-Click Access</span>
              </div>
              <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2.5 py-0.5 rounded-full border border-emerald-500/25">
                READY
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <button
                type="button"
                disabled={loading}
                onClick={() => handleQuickLogin('reviewer', 'password123')}
                className="p-3 rounded-xl bg-indigo-600/25 hover:bg-indigo-600/40 border border-indigo-500/40 text-indigo-200 text-sm font-semibold flex flex-col items-center justify-center gap-1.5 transition-all hover:scale-[1.02] cursor-pointer"
              >
                <div className="flex items-center gap-1.5">
                  <span>⚡</span>
                  <span className="font-bold">Reviewer</span>
                </div>
                <span className="text-xs text-indigo-300/90 font-normal">Triage & Approval Tokens</span>
              </button>
              <button
                type="button"
                disabled={loading}
                onClick={() => handleQuickLogin('admin', 'admin_secret_2026')}
                className="p-3 rounded-xl bg-purple-600/25 hover:bg-purple-600/40 border border-purple-500/40 text-purple-200 text-sm font-semibold flex flex-col items-center justify-center gap-1.5 transition-all hover:scale-[1.02] cursor-pointer"
              >
                <div className="flex items-center gap-1.5">
                  <span>🛡️</span>
                  <span className="font-bold">Admin</span>
                </div>
                <span className="text-xs text-purple-300/90 font-normal">Settings & Webhooks</span>
              </button>
            </div>
          </div>
        )}

        {/* Tab Switcher */}
        <div className="flex rounded-xl bg-slate-900/80 p-1.5 mb-6 border border-slate-800">
          <button
            type="button"
            onClick={() => {
              setMode('login');
              setError(null);
            }}
            className={`flex-1 py-2 text-sm font-semibold rounded-lg transition-all ${
              mode === 'login'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Sign In
          </button>
          {allowRegistration ? (
            <button
              type="button"
              onClick={() => {
                setMode('register');
                setError(null);
              }}
              className={`flex-1 py-2 text-sm font-semibold rounded-lg transition-all ${
                mode === 'register'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Create Account
            </button>
          ) : (
            <div
              className="flex-1 py-2 text-sm font-semibold rounded-lg text-slate-500 text-center cursor-not-allowed"
              title="Open self-registration is disabled in production"
            >
              Registration Disabled
            </div>
          )}
        </div>

        {error && (
          <div className="mb-4 p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-2.5">
            <AlertCircle className="w-4 h-4 flex-shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="mb-4 p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm flex items-center gap-2.5">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0 text-emerald-400" />
            <span>{success}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'register' && (
            <div>
              <label className="block text-sm font-semibold text-slate-300 mb-1.5">Full Name</label>
              <input
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="e.g. Priya Sharma"
                className="input-control text-sm h-11 rounded-xl"
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-semibold text-slate-300 mb-1.5 flex items-center gap-1.5">
              <User className="w-4 h-4 text-slate-400" />
              <span>Username</span>
            </label>
            <input
              id="input-login-username"
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. psharma"
              className="input-control text-sm h-11 rounded-xl"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-slate-300 mb-1.5 flex items-center gap-1.5">
              <Key className="w-4 h-4 text-slate-400" />
              <span>Password</span>
            </label>
            <input
              id="input-login-password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              className="input-control text-sm h-11 rounded-xl"
            />
          </div>

          {mode === 'register' && (
            <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800 text-sm">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-slate-300">Initial Account Role</span>
                <span className="badge badge-open text-xs uppercase font-mono">Reviewer</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                Self-registration automatically grants Merchant Reviewer access. Elevated privileges (Administrator, Compliance Auditor) must be granted by an authenticated Admin.
              </p>
            </div>
          )}

          <div className="pt-2 flex flex-col gap-2.5">
            <button
              id="btn-submit-login"
              type="submit"
              disabled={loading}
              className="btn btn-primary w-full h-11 text-sm font-semibold flex items-center justify-center gap-2 rounded-xl"
            >
              {loading ? (
                <span>Processing...</span>
              ) : mode === 'login' ? (
                <>
                  <span>Sign In to Console</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              ) : (
                <>
                  <UserPlus className="w-4 h-4" />
                  <span>Register & Launch</span>
                </>
              )}
            </button>

            {isDemoAllowed && mode === 'login' && (
              <div className="flex items-center justify-center gap-3 pt-1">
                <button
                  id="btn-fill-demo"
                  type="button"
                  onClick={() => handleFillDemo('reviewer')}
                  className="btn btn-ghost text-xs text-indigo-400 font-semibold hover:text-indigo-300"
                >
                  Fill Reviewer Demo
                </button>
                <span className="text-slate-600">•</span>
                <button
                  type="button"
                  onClick={() => handleFillDemo('admin')}
                  className="btn btn-ghost text-xs text-indigo-400 font-semibold hover:text-indigo-300"
                >
                  Fill Admin Demo
                </button>
              </div>
            )}
          </div>
        </form>

        <div className="mt-6 pt-4 border-t border-slate-800/80 text-center text-xs text-slate-400">
          Secured with scrypt hashing, HMAC-signed session cookies, and CSRF token validation.
        </div>
      </div>
    </div>
  );
}

import React, { useState } from 'react';
import { Shield, Key, AlertCircle, ArrowRight, Lock, User, UserPlus, Sparkles, CheckCircle2 } from 'lucide-react';
import { login, registerUser } from '../api';

export default function LoginModal({ isOpen, onClose, onLoginSuccess }) {
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [username, setUsername] = useState('reviewer');
  const [password, setPassword] = useState('password123');
  const [fullName, setFullName] = useState('');
  const [role, setRole] = useState('reviewer'); // 'reviewer' | 'auditor' | 'admin'
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

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

  function handleFillDemo(demoRole = 'reviewer') {
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
      <div className="modal-content p-6 sm:p-8 relative max-w-md">
        {/* Header */}
        <div className="text-center mb-6">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-cyan-400 p-[1.5px] mx-auto mb-3 shadow-lg shadow-indigo-500/20">
            <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center text-indigo-400">
              <Shield className="w-6 h-6" />
            </div>
          </div>
          <h3 className="font-heading text-2xl font-bold text-white mb-1">
            {mode === 'login' ? 'Merchant Console Access' : 'Create Merchant Account'}
          </h3>
          <p className="text-xs text-slate-400">
            {mode === 'login'
              ? 'Sign in to access automated dispute defense and approval tokens.'
              : 'Register a new reviewer or compliance auditor for your organization.'}
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="flex rounded-lg bg-slate-900/80 p-1 mb-6 border border-slate-800">
          <button
            type="button"
            onClick={() => {
              setMode('login');
              setError(null);
            }}
            className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-all ${
              mode === 'login'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => {
              setMode('register');
              setError(null);
            }}
            className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-all ${
              mode === 'register'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Create Account
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="mb-4 p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0 text-emerald-400" />
            <span>{success}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {mode === 'register' && (
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">Full Name</label>
              <input
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="e.g. Priya Sharma"
                className="input-control text-xs"
              />
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5 flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-slate-400" />
              <span>Username</span>
            </label>
            <input
              id="input-login-username"
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. psharma"
              className="input-control text-xs"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1.5 flex items-center gap-1.5">
              <Key className="w-3.5 h-3.5 text-slate-400" />
              <span>Password</span>
            </label>
            <input
              id="input-login-password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              className="input-control text-xs"
            />
          </div>

          {mode === 'register' && (
            <div>
              <label className="block text-xs font-semibold text-slate-300 mb-1.5">Role Permission</label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="input-control text-xs"
              >
                <option value="reviewer">Reviewer (Can draft and approve disputes)</option>
                <option value="auditor">Compliance Auditor (Read-only audit ledger)</option>
                <option value="admin">Admin (Full administrative privileges)</option>
              </select>
            </div>
          )}

          <div className="pt-2 flex flex-col gap-2">
            <button
              id="btn-submit-login"
              type="submit"
              disabled={loading}
              className="btn btn-primary w-full py-2.5 text-xs font-semibold flex items-center justify-center gap-2"
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

            {mode === 'login' && (
              <div className="flex items-center justify-center gap-3 pt-1">
                <button
                  id="btn-fill-demo"
                  type="button"
                  onClick={() => handleFillDemo('reviewer')}
                  className="btn btn-ghost text-[11px] text-indigo-400 hover:text-indigo-300"
                >
                  Fill Reviewer Demo
                </button>
                <span className="text-slate-600">•</span>
                <button
                  type="button"
                  onClick={() => handleFillDemo('admin')}
                  className="btn btn-ghost text-[11px] text-indigo-400 hover:text-indigo-300"
                >
                  Fill Admin Demo
                </button>
              </div>
            )}
          </div>
        </form>

        <div className="mt-6 pt-4 border-t border-slate-800/80 text-center text-[11px] text-slate-500">
          Secured with scrypt hashing, HMAC-signed session cookies, and CSRF token validation.
        </div>
      </div>
    </div>
  );
}

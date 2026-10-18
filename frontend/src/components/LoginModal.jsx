import React, { useState } from 'react';
import { Shield, Key, AlertCircle, CheckCircle, ArrowRight, Lock, User } from 'lucide-react';
import { login } from '../api';

export default function LoginModal({ isOpen, onClose, onLoginSuccess }) {
  const [username, setUsername] = useState('reviewer');
  const [password, setPassword] = useState('password123');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  async function handleSubmit(e) {
    if (e) e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      const data = await login(username, password);
      onLoginSuccess(data.user);
      onClose();
    } catch (err) {
      setError(err.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  }

  function handleFillDemo() {
    setUsername('reviewer');
    setPassword('password123');
    setError(null);
  }


  return (
    <div className="modal-overlay">
      <div className="modal-content p-6 sm:p-8 relative">
        <div className="text-center mb-6">
          <div className="w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center mx-auto mb-3 text-indigo-400">
            <Lock className="w-6 h-6" />
          </div>
          <h3 className="font-heading text-2xl font-bold text-white mb-1">Reviewer Authentication</h3>
          <p className="text-xs text-slate-400">
            Sign in with merchant reviewer credentials to access disputes and approval tokens.
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
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
              placeholder="e.g. Priya Sharma"
              className="input-control"
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
              className="input-control"
            />
          </div>

          <div className="pt-2 flex flex-col gap-2">
            <button
              id="btn-submit-login"
              type="submit"
              disabled={loading}
              className="btn btn-primary w-full py-2.5 text-sm"
            >
              {loading ? (
                <span>Authenticating...</span>
              ) : (
                <>
                  <span>Sign In to Console</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>

            <button
              id="btn-fill-demo"
              type="button"
              onClick={handleFillDemo}
              className="btn btn-ghost text-xs text-indigo-400 hover:text-indigo-300 w-full"
            >
              Auto-fill Demo Credentials
            </button>
          </div>
        </form>

        <div className="mt-6 pt-4 border-t border-slate-800/80 text-center text-[11px] text-slate-500">
          Secured with HMAC-signed session cookies and cryptographic CSRF token validation.
        </div>
      </div>
    </div>
  );
}

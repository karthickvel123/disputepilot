import React from 'react';
import { Shield, LayoutDashboard, FileText, History, Settings, LogOut, ExternalLink, Sparkles, AlertCircle } from 'lucide-react';

export default function Navbar({ activeTab, setActiveTab, user, onLogout, systemSettings, onOpenLanding }) {
  const isSim = systemSettings?.data_mode === 'sim';

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-800 bg-slate-950/80 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        
        {/* Brand / Logo */}
        <div className="flex items-center gap-3 cursor-pointer" onClick={onOpenLanding}>
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-cyan-400 p-[1.5px] shadow-lg shadow-indigo-500/25">
            <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
              <Shield className="w-5 h-5 text-indigo-400" />
            </div>
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-heading text-lg font-bold tracking-tight text-white">DisputePilot</span>
              <span className="text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded bg-indigo-500/15 text-indigo-400 border border-indigo-500/30">
                AI REVIEWS
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-sans hidden sm:block">Razorpay Dispute Defense</p>
          </div>
        </div>

        {/* Navigation Tabs */}
        {user && (
          <nav className="hidden md:flex items-center gap-1">
            <button
              id="nav-dashboard"
              onClick={() => setActiveTab('dashboard')}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'dashboard'
                  ? 'bg-indigo-600/15 text-indigo-400 border border-indigo-500/30 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
              }`}
            >
              <LayoutDashboard className="w-4 h-4" />
              <span>Dashboard</span>
            </button>

            <button
              id="nav-disputes"
              onClick={() => setActiveTab('disputes')}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'disputes' || activeTab === 'detail'
                  ? 'bg-indigo-600/15 text-indigo-400 border border-indigo-500/30 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
              }`}
            >
              <FileText className="w-4 h-4" />
              <span>Disputes</span>
            </button>

            <button
              id="nav-audit"
              onClick={() => setActiveTab('audit')}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'audit'
                  ? 'bg-indigo-600/15 text-indigo-400 border border-indigo-500/30 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
              }`}
            >
              <History className="w-4 h-4" />
              <span>Audit Ledger</span>
            </button>

            <button
              id="nav-settings"
              onClick={() => setActiveTab('settings')}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'settings'
                  ? 'bg-indigo-600/15 text-indigo-400 border border-indigo-500/30 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
              }`}
            >
              <Settings className="w-4 h-4" />
              <span>Settings</span>
            </button>
          </nav>
        )}

        {/* Right side controls */}
        <div className="flex items-center gap-3">
          {/* Data Mode Pill */}
          <div
            className={`hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-medium border ${
              isSim
                ? 'bg-amber-500/10 text-amber-400 border-amber-500/30'
                : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
            }`}
            title={isSim ? "Operating in synthetic evaluation simulation mode" : "Connected to live Razorpay API"}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${isSim ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'}`}></span>
            <span>{isSim ? 'SIMULATION' : 'RAZORPAY LIVE'}</span>
          </div>

          {user ? (
            <div className="flex items-center gap-3 pl-2 border-l border-slate-800">
              <div className="text-right hidden sm:block">
                <div className="text-xs font-medium text-slate-200">{user}</div>
                <div className="text-[10px] text-slate-400">Authorized Reviewer</div>
              </div>
              <button
                id="btn-logout"
                onClick={onLogout}
                className="btn btn-ghost text-xs p-2 text-slate-400 hover:text-rose-400"
                title="Sign out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <button
              id="btn-launch-login"
              onClick={() => setActiveTab('dashboard')}
              className="btn btn-primary text-xs"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Reviewer Console</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

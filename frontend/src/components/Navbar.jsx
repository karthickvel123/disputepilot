import React, { useState, useEffect, useRef } from 'react';
import { 
  Shield, 
  LayoutDashboard, 
  FileText, 
  History, 
  Settings, 
  LogOut, 
  ExternalLink, 
  Sparkles, 
  AlertCircle,
  Bell,
  ShieldCheck,
  CheckCircle2,
  Clock,
  User,
  ChevronDown,
  X
} from 'lucide-react';
import { getNotifications, markNotificationRead } from '../api';

export default function Navbar({ 
  activeTab, 
  setActiveTab, 
  user, 
  userRole = 'reviewer', 
  onLogout, 
  systemSettings, 
  onOpenLanding,
  onQuickDemoLogin,
  onSimulateDispute
}) {
  const isSim = systemSettings?.data_mode === 'sim';

  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);
  const notifRef = useRef(null);

  useEffect(() => {
    if (user) {
      loadNotifications();
      const interval = setInterval(loadNotifications, 45000);
      return () => clearInterval(interval);
    }
  }, [user]);

  // Click outside to close notifications
  useEffect(() => {
    function handleClickOutside(event) {
      if (notifRef.current && !notifRef.current.contains(event.target)) {
        setNotifOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  async function loadNotifications() {
    try {
      const data = await getNotifications();
      setNotifications(data.notifications || []);
      setUnreadCount(data.unread_count || 0);
    } catch {
      // ignore in silent polling
    }
  }

  async function handleNotificationClick(notif) {
    try {
      await markNotificationRead(notif.id);
      setNotifications((prev) => prev.filter((n) => n.id !== notif.id));
      setUnreadCount((c) => Math.max(0, c - 1));
      if (notif.case_id) {
        setNotifOpen(false);
        setActiveTab('disputes');
      }
    } catch {
      // ignore
    }
  }

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
              <span>Worklist</span>
            </button>

            <button
              id="nav-review-queue"
              onClick={() => setActiveTab('review-queue')}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === 'review-queue'
                  ? 'bg-indigo-600/15 text-indigo-400 border border-indigo-500/30 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
              }`}
            >
              <ShieldCheck className="w-4 h-4" />
              <span>Review Queue</span>
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
            <div className="flex items-center gap-3 pl-2 border-l border-slate-800 relative">
              {/* Quick Simulate Dispute Button */}
              {onSimulateDispute && (
                <button
                  type="button"
                  onClick={onSimulateDispute}
                  className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-r from-indigo-500/20 via-cyan-500/15 to-indigo-500/20 hover:from-indigo-500/30 hover:to-cyan-500/25 border border-indigo-500/40 text-indigo-200 text-xs font-semibold shadow-sm transition-all hover:scale-[1.02] cursor-pointer"
                  title="Generate a new realistic dispute to test automated AI triage in real time"
                >
                  <Sparkles className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
                  <span>+ Simulate Dispute</span>
                </button>
              )}

              {/* Notifications Bell */}
              <div className="relative" ref={notifRef}>
                <button
                  id="btn-notifications"
                  onClick={() => setNotifOpen(!notifOpen)}
                  className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-900/90 relative transition-colors cursor-pointer border border-transparent hover:border-slate-800"
                  title="Notifications"
                >
                  <Bell className="w-4 h-4" />
                  {unreadCount > 0 && (
                    <span className="absolute top-1 right-1 w-2.5 h-2.5 rounded-full bg-rose-500 animate-ping"></span>
                  )}
                  {unreadCount > 0 && (
                    <span className="absolute top-1 right-1 w-2.5 h-2.5 rounded-full bg-rose-500 border border-slate-950"></span>
                  )}
                </button>

                {/* Notifications Dropdown */}
                {notifOpen && (
                  <div className="absolute right-0 mt-2 w-80 sm:w-96 glass-panel-premium border border-slate-700/80 shadow-2xl rounded-xl z-50 divide-y divide-slate-800/80 overflow-hidden animate-fade-in">
                    <div className="p-3.5 bg-slate-900/90 flex items-center justify-between border-b border-slate-800">
                      <span className="text-xs font-bold text-white flex items-center gap-1.5">
                        <Bell className="w-3.5 h-3.5 text-indigo-400" />
                        <span>System Notifications</span>
                      </span>
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                        {notifications.length} alerts
                      </span>
                    </div>

                    <div className="max-h-80 overflow-y-auto divide-y divide-slate-800/40 text-xs">
                      {notifications.length === 0 ? (
                        <div className="p-6 text-center text-slate-400 text-xs">
                          No pending alerts or notifications.
                        </div>
                      ) : (
                        notifications.map((n) => (
                          <div
                            key={n.id}
                            onClick={() => handleNotificationClick(n)}
                            className="p-3.5 hover:bg-slate-900/70 cursor-pointer transition-colors"
                          >
                            <div className="flex items-start justify-between gap-2 mb-1">
                              <span className={`font-semibold flex items-center gap-1.5 ${
                                n.type === 'urgent' ? 'text-rose-400' : n.type === 'warning' ? 'text-amber-400' : 'text-indigo-400'
                              }`}>
                                {n.type === 'urgent' ? (
                                  <Clock className="w-3 h-3 text-rose-400 animate-pulse flex-shrink-0" />
                                ) : (
                                  <Shield className="w-3 h-3 text-indigo-400 flex-shrink-0" />
                                )}
                                <span>{n.title}</span>
                              </span>
                              {n.case_id && (
                                <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                                  {n.case_id}
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-slate-300 leading-snug">{n.message}</p>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                )}
              </div>

              {/* User profile with avatar initial */}
              <div className="flex items-center gap-2 pl-1">
                <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-indigo-500 to-cyan-400 p-[1px] shadow-sm shadow-indigo-500/30">
                  <div className="w-full h-full bg-slate-950 rounded-full flex items-center justify-center text-[11px] font-bold text-white uppercase">
                    {user?.charAt(0) || 'U'}
                  </div>
                </div>
                <div className="text-right hidden sm:block">
                  <div className="text-xs font-semibold text-slate-200">{user}</div>
                  <div className="text-[10px] font-mono capitalize text-indigo-400">{userRole}</div>
                </div>
              </div>

              <button
                id="btn-logout"
                onClick={onLogout}
                className="btn btn-ghost text-xs p-2 text-slate-400 hover:text-rose-400 rounded-lg"
                title="Sign out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <button
                id="btn-nav-quick-demo"
                onClick={onQuickDemoLogin || (() => setActiveTab('dashboard'))}
                className="btn bg-gradient-to-r from-indigo-600 via-indigo-500 to-cyan-500 hover:from-indigo-500 hover:to-cyan-400 text-white font-semibold text-xs shadow-md shadow-indigo-500/25 flex items-center gap-1.5 hover:-translate-y-0.5 transition-all"
                title="Instant one-click access as Merchant Reviewer"
              >
                <Sparkles className="w-3.5 h-3.5 text-cyan-200" />
                <span>1-Click Demo</span>
              </button>
              <button
                id="btn-launch-login"
                onClick={() => setActiveTab('dashboard')}
                className="btn btn-secondary text-xs text-slate-300"
              >
                <span>Sign In</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}



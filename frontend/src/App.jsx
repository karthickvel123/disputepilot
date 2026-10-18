import React, { useState, useEffect } from 'react';
import Navbar from './components/Navbar';
import LandingPage from './components/LandingPage';
import DashboardView from './components/DashboardView';
import DisputesView from './components/DisputesView';
import CaseDetailView from './components/CaseDetailView';
import ReviewQueueView from './components/ReviewQueueView';
import AuditLedgerView from './components/AuditLedgerView';
import SettingsView from './components/SettingsView';
import LoginModal from './components/LoginModal';
import { getMe, logout, getDashboardMetrics, getSettings } from './api';

export default function App() {
  const [user, setUser] = useState(null);
  const [userRole, setUserRole] = useState('reviewer');
  const [activeView, setActiveView] = useState('landing'); // 'landing' | 'dashboard' | 'disputes' | 'review-queue' | 'detail' | 'audit' | 'settings'
  const [selectedCaseId, setSelectedCaseId] = useState(null);
  const [disputeFilter, setDisputeFilter] = useState('all');
  const [loginModalOpen, setLoginModalOpen] = useState(false);

  const [metrics, setMetrics] = useState(null);
  const [systemSettings, setSystemSettings] = useState(null);

  useEffect(() => {
    // Check existing session
    checkSession();
    fetchInitialData();

    // Listen for 401s
    function handleUnauthorized() {
      setUser(null);
      setLoginModalOpen(true);
    }
    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized);
  }, []);

  async function checkSession() {
    try {
      const me = await getMe();
      if (me?.user) {
        setUser(me.user);
        if (me?.role) setUserRole(me.role);
      }
    } catch {
      // Not logged in; keep user null
    }
  }

  async function fetchInitialData() {
    try {
      const [m, s] = await Promise.allSettled([
        getDashboardMetrics(),
        getSettings(),
      ]);
      if (m.status === 'fulfilled') setMetrics(m.value);
      if (s.status === 'fulfilled') setSystemSettings(s.value);
    } catch (e) {
      console.warn('Initial data load error:', e);
    }
  }

  async function handleLogout() {
    try {
      await logout();
    } catch (e) {
      console.error(e);
    }
    setUser(null);
    setActiveView('landing');
  }

  function handleLoginSuccess(username, role = 'reviewer') {
    setUser(username);
    setUserRole(role);
    setLoginModalOpen(false);
    fetchInitialData();
    if (activeView === 'landing') {
      setActiveView('dashboard');
    }
  }

  function handleNavigateToDisputes(filter = 'all') {
    setDisputeFilter(filter);
    setActiveView('disputes');
  }

  function handleSelectCase(caseId) {
    setSelectedCaseId(caseId);
    setActiveView('detail');
  }

  function handleBackToWorklist() {
    setSelectedCaseId(null);
    setActiveView('disputes');
  }

  function handleLaunchConsole() {
    if (user) {
      setActiveView('dashboard');
    } else {
      setLoginModalOpen(true);
    }
  }

  return (
    <div className="min-h-screen bg-mesh text-slate-100 flex flex-col font-sans">
      <Navbar
        activeTab={activeView}
        setActiveTab={(tab) => {
          if (!user && tab !== 'landing') {
            setLoginModalOpen(true);
            return;
          }
          setActiveView(tab);
        }}
        user={user}
        userRole={userRole}
        onLogout={handleLogout}
        systemSettings={systemSettings}
        onOpenLanding={() => setActiveView('landing')}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        {activeView === 'landing' && (
          <LandingPage
            onLaunchConsole={handleLaunchConsole}
            metrics={metrics}
          />
        )}

        {activeView === 'dashboard' && (
          <DashboardView
            metrics={metrics}
            onSelectDispute={handleSelectCase}
            onNavigateToDisputes={handleNavigateToDisputes}
          />
        )}

        {activeView === 'disputes' && (
          <DisputesView
            initialFilter={disputeFilter}
            onSelectCase={handleSelectCase}
          />
        )}

        {activeView === 'review-queue' && (
          <ReviewQueueView
            onSelectCase={handleSelectCase}
          />
        )}

        {activeView === 'detail' && selectedCaseId && (
          <CaseDetailView
            caseId={selectedCaseId}
            onBack={handleBackToWorklist}
            onCaseUpdated={fetchInitialData}
          />
        )}

        {activeView === 'audit' && (
          <AuditLedgerView
            onSelectCase={handleSelectCase}
          />
        )}

        {activeView === 'settings' && (
          <SettingsView />
        )}
      </main>

      {/* Login Modal */}
      <LoginModal
        isOpen={loginModalOpen}
        onClose={() => setLoginModalOpen(false)}
        onLoginSuccess={handleLoginSuccess}
      />

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950 py-6 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-heading font-bold text-slate-300">DisputePilot</span>
            <span>— AI-Driven Payment Dispute Defense Platform for Razorpay</span>
          </div>
          <div className="flex items-center gap-4 text-slate-400">
            <span>Deterministic Verifier</span>
            <span>•</span>
            <span>PCI-DSS Shield</span>
            <span>•</span>
            <span>SHA-256 Hash Chain</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

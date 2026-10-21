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
import { getMe, logout, login, register, createDispute, getDashboardMetrics, getSettings } from './api';

export default function App() {
  const [user, setUser] = useState(null);
  const [userRole, setUserRole] = useState('reviewer');
  const [activeView, setActiveView] = useState('landing'); // 'landing' | 'dashboard' | 'disputes' | 'review-queue' | 'detail' | 'audit' | 'settings'
  const [selectedCaseId, setSelectedCaseId] = useState(null);
  const [disputeFilter, setDisputeFilter] = useState('all');
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);

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

  function showToast(msg) {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage((current) => (current === msg ? null : current));
    }, 4500);
  }

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
    showToast(`Signed in successfully as ${username} (${role}).`);
    if (activeView === 'landing') {
      setActiveView('dashboard');
    }
  }

  async function handleQuickDemoLogin() {
    try {
      const data = await login('reviewer', 'password123');
      handleLoginSuccess(data.user, data.role);
    } catch (e) {
      try {
        const reg = await register('reviewer', 'password123', 'Authorized Reviewer');
        handleLoginSuccess(reg.user, reg.role);
      } catch (err) {
        console.warn('Quick login error, opening modal:', err);
        setLoginModalOpen(true);
      }
    }
  }

  async function handleSimulateDispute() {
    const randomId = Math.floor(1000 + Math.random() * 9000);
    const carrierList = ['Delhivery', 'BlueDart', 'DTDC', 'IndiaPost'];
    const carrier = carrierList[Math.floor(Math.random() * carrierList.length)];
    const scenarios = [
      {
        reason_code: 'item_not_received',
        reason_description: 'Customer claims merchant failed to deliver electronics package on time.',
        amount: 3499,
      },
      {
        reason_code: 'unauthorised',
        reason_description: 'Cardholder claims unauthorized recurring charge via stored payment token.',
        amount: 5999,
      },
      {
        reason_code: 'not_as_described',
        reason_description: 'Buyer claims product delivered differs in specifications from catalogue.',
        amount: 2199,
      },
    ];
    const scenario = scenarios[Math.floor(Math.random() * scenarios.length)];

    try {
      showToast('⚡ Ingesting incoming Razorpay webhook dispute...');
      const res = await createDispute({
        dispute_id: `disp_sim_${randomId}`,
        amount_rupees: scenario.amount,
        currency: 'INR',
        reason_code: scenario.reason_code,
        reason_description: scenario.reason_description,
        customer_name: 'Simulated Merchant Buyer',
        customer_email: `buyer_${randomId}@example.com`,
        customer_phone: '+91 98765 43210',
        shipping_carrier: carrier,
        tracking_number: `${carrier.toUpperCase().slice(0, 3)}${randomId}982IN`,
        days_to_respond: 5,
      });

      showToast(`⚡ Dispute '${res.dispute_id}' created & triaged autonomously!`);
      await fetchInitialData();
      if (activeView === 'landing') {
        setActiveView('disputes');
      }
    } catch (err) {
      showToast(`Simulation failed: ${err.message || 'Error creating dispute'}`);
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
      {/* Global Notification Toast */}
      {toastMessage && (
        <div className="fixed top-18 right-6 z-50 p-4 rounded-xl bg-slate-900/95 border border-indigo-500/40 text-indigo-200 text-xs shadow-2xl backdrop-blur-md flex items-center gap-3 animate-slide-in">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
          <span className="font-medium text-white">{toastMessage}</span>
          <button
            onClick={() => setToastMessage(null)}
            className="text-slate-400 hover:text-white ml-2 text-sm"
          >
            ✕
          </button>
        </div>
      )}

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
        onQuickDemoLogin={handleQuickDemoLogin}
        onSimulateDispute={handleSimulateDispute}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        {activeView === 'landing' && (
          <LandingPage
            onLaunchConsole={handleLaunchConsole}
            onQuickDemoLogin={handleQuickDemoLogin}
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

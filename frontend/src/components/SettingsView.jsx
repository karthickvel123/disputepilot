import React, { useState, useEffect } from 'react';
import { 
  Settings, 
  Shield, 
  Key, 
  CheckCircle2, 
  AlertTriangle, 
  Cpu, 
  Server, 
  Webhook, 
  ExternalLink,
  RefreshCw,
  FileText,
  Building,
  Lock,
  Users,
  Activity,
  Send,
  Save,
  Check
} from 'lucide-react';
import { 
  getSettings, 
  getOrgSettings, 
  saveOrgSettings, 
  changePassword, 
  listUsers,
  updateUserRole,
  testRazorpayConnection, 
  testAiConnection 
} from '../api';

export default function SettingsView() {
  const [activeTab, setActiveTab] = useState('diagnostics'); // 'diagnostics' | 'org' | 'security'
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  // Diagnostics test states
  const [testingRzp, setTestingRzp] = useState(false);
  const [rzpResult, setRzpResult] = useState(null);
  const [testingAi, setTestingAi] = useState(false);
  const [aiResult, setAiResult] = useState(null);

  // Organization settings state
  const [orgSettings, setOrgSettings] = useState({
    merchant_name: '',
    merchant_id: '',
    currency: 'INR',
    timezone: 'Asia/Kolkata',
    auto_triage: true,
    high_value_threshold_paise: 5000000,
    contact_email: '',
  });
  const [savingOrg, setSavingOrg] = useState(false);

  // Change password state
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changingPw, setChangingPw] = useState(false);

  // Users list
  const [users, setUsers] = useState([]);
  const [usersError, setUsersError] = useState(null);

  useEffect(() => {
    loadAllSettings();
  }, []);

  async function loadAllSettings() {
    setLoading(true);
    setError(null);
    try {
      const [sys, org, uList] = await Promise.allSettled([
        getSettings(),
        getOrgSettings(),
        listUsers(),
      ]);
      if (sys.status === 'fulfilled') setSettings(sys.value);
      if (org.status === 'fulfilled') setOrgSettings(org.value);
      if (uList.status === 'fulfilled') {
        setUsers(uList.value.users || []);
        setUsersError(null);
      } else {
        setUsersError(uList.reason?.message || 'Team member access is unavailable.');
      }
    } catch (err) {
      setError(err.message || 'Failed to fetch settings.');
    } finally {
      setLoading(false);
    }
  }

  async function handleTestRazorpay() {
    setTestingRzp(true);
    setRzpResult(null);
    try {
      const res = await testRazorpayConnection();
      setRzpResult(res);
    } catch (err) {
      setRzpResult({ status: 'error', message: err.message });
    } finally {
      setTestingRzp(false);
    }
  }

  async function handleTestAi() {
    setTestingAi(true);
    setAiResult(null);
    try {
      const res = await testAiConnection();
      setAiResult(res);
    } catch (err) {
      setAiResult({ status: 'error', message: err.message });
    } finally {
      setTestingAi(false);
    }
  }

  async function handleSaveOrg(e) {
    if (e) e.preventDefault();
    setSavingOrg(true);
    setSuccess(null);
    setError(null);
    try {
      await saveOrgSettings(orgSettings);
      setSuccess('Organization profile and triage rules saved successfully.');
    } catch (err) {
      setError(`Failed to save organization settings: ${err.message}`);
    } finally {
      setSavingOrg(false);
    }
  }

  async function handleChangePassword(e) {
    if (e) e.preventDefault();
    if (newPassword !== confirmPassword) {
      setError('New passwords do not match.');
      return;
    }
    setChangingPw(true);
    setSuccess(null);
    setError(null);
    try {
      await changePassword({ old_password: oldPassword, new_password: newPassword });
      setSuccess('Password updated successfully.');
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      setError(err.message || 'Password update failed.');
    } finally {
      setChangingPw(false);
    }
  }

  async function handleRoleChange(username, newRole) {
    setError(null);
    setSuccess(null);
    try {
      await updateUserRole(username, newRole);
      setUsers(users.map(u => u.username === username ? { ...u, role: newRole } : u));
      setSuccess(`Role for '${username}' updated to '${newRole}'.`);
    } catch (err) {
      setError(err.message || 'Failed to update user role.');
    }
  }

  if (loading) {
    return (
      <div className="py-20 text-center">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
        <p className="text-slate-400 text-xs">Loading system configuration...</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-fade-in pb-16">
      {/* Header */}
      <div className="border-b border-slate-800 pb-5">
        <h2 className="font-heading text-2xl sm:text-3xl font-bold text-white flex items-center gap-2">
          <Settings className="w-7 h-7 text-indigo-400" />
          <span>System Settings & Organization Center</span>
        </h2>
        <p className="text-sm text-slate-400 mt-1.5">
          Manage live API gateways, AI reasoning models, organization profile rules, and reviewer credentials.
        </p>
      </div>

      {success && (
        <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm flex items-center gap-2.5">
          <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
          <span>{success}</span>
        </div>
      )}

      {error && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-2.5">
          <AlertTriangle className="w-5 h-5 text-rose-400 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Tabs */}
      <div className="flex items-center gap-8 border-b border-slate-800 text-sm">
        <button
          onClick={() => {
            setActiveTab('diagnostics');
            setError(null);
            setSuccess(null);
          }}
          className={`pb-3.5 font-semibold flex items-center gap-2 border-b-2 transition-all ${
            activeTab === 'diagnostics'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Activity className="w-4 h-4" />
          <span>Gateway & AI Diagnostics</span>
        </button>

        <button
          onClick={() => {
            setActiveTab('org');
            setError(null);
            setSuccess(null);
          }}
          className={`pb-3.5 font-semibold flex items-center gap-2 border-b-2 transition-all ${
            activeTab === 'org'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Building className="w-4 h-4" />
          <span>Organization & Automation</span>
        </button>

        <button
          onClick={() => {
            setActiveTab('security');
            setError(null);
            setSuccess(null);
          }}
          className={`pb-3.5 font-semibold flex items-center gap-2 border-b-2 transition-all ${
            activeTab === 'security'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Lock className="w-4 h-4" />
          <span>Security & Team Access</span>
        </button>
      </div>

      {/* Tab 1: Diagnostics */}
      {activeTab === 'diagnostics' && (
        <div className="space-y-6">
          {/* Integration Status Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            {/* Razorpay Gateway */}
            <div className="glass-panel-premium card-sheen p-6 space-y-4 relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-indigo-500 to-purple-500" />
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/25 flex items-center justify-center text-indigo-400 shadow-sm">
                    <Server className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-heading text-base font-bold text-white">Razorpay Disputes Gateway</h3>
                    <p className="text-xs text-slate-400">Direct payment partner integration</p>
                  </div>
                </div>
                <span className={`badge ${settings?.has_razorpay ? 'badge-won' : 'badge-urgent'}`}>
                  {settings?.has_razorpay ? 'CONFIGURED' : 'SIMULATION MODE'}
                </span>
              </div>

              <div className="space-y-3 text-sm pt-1">
                <div className="flex justify-between py-1.5 border-b border-slate-800/60">
                  <span className="text-slate-400">Data Mode</span>
                  <span className="font-mono text-indigo-400 uppercase font-semibold">{settings?.data_mode}</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-slate-800/60">
                  <span className="text-slate-400">Key Mode</span>
                  <span className="font-mono text-slate-300 uppercase">{settings?.key_mode}</span>
                </div>
                <div className="flex justify-between py-1.5">
                  <span className="text-slate-400">Base API URL</span>
                  <span className="font-mono text-slate-400 truncate max-w-[200px]" title={settings?.razorpay_base_url}>
                    {settings?.razorpay_base_url}
                  </span>
                </div>
              </div>

              <div className="pt-2 border-t border-slate-800/80">
                <button
                  type="button"
                  onClick={handleTestRazorpay}
                  disabled={testingRzp}
                  className="btn btn-secondary h-11 text-sm font-semibold w-full flex items-center justify-center gap-2 rounded-xl"
                >
                  <RefreshCw className={`w-4 h-4 ${testingRzp ? 'animate-spin' : ''}`} />
                  <span>{testingRzp ? 'Testing Connection...' : 'Test Razorpay Connection'}</span>
                </button>

                {rzpResult && (
                  <div className={`mt-3 p-3.5 rounded-xl text-xs ${
                    rzpResult.status === 'error'
                      ? 'bg-rose-500/10 text-rose-300 border border-rose-500/30'
                      : 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30'
                  }`}>
                    <div className="font-bold mb-1 text-sm">
                      Status: {rzpResult.status} ({rzpResult.latency_ms}ms)
                    </div>
                    <div>{rzpResult.message}</div>
                  </div>
                )}
              </div>
            </div>

            {/* Gemini AI Engine */}
            <div className="glass-panel-premium card-sheen p-6 space-y-4 relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-cyan-500 to-blue-500" />
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/25 flex items-center justify-center text-cyan-400 shadow-sm">
                    <Cpu className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="font-heading text-base font-bold text-white">Gemini Multimodal AI</h3>
                    <p className="text-xs text-slate-400">Automated defense reasoning engine</p>
                  </div>
                </div>
                <span className={`badge ${settings?.has_llm ? 'badge-won' : 'badge-open'}`}>
                  {settings?.has_llm ? 'ONLINE' : 'ACTIVE RULES'}
                </span>
              </div>

              <div className="space-y-3 text-sm pt-1">
                <div className="flex justify-between py-1.5 border-b border-slate-800/60">
                  <span className="text-slate-400">Model Engine</span>
                  <span className="font-mono text-cyan-400 font-semibold">Gemini 2.5 Flash / 1.5 Pro</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-slate-800/60">
                  <span className="text-slate-400">SDK Status</span>
                  <span className="font-mono text-slate-300">google-genai / Deterministic Rules</span>
                </div>
                <div className="flex justify-between py-1.5">
                  <span className="text-slate-400">Hallucination Guard</span>
                  <span className="font-medium text-emerald-400">Deterministic Citation Grounding</span>
                </div>
              </div>

              <div className="pt-2 border-t border-slate-800/80">
                <button
                  type="button"
                  onClick={handleTestAi}
                  disabled={testingAi}
                  className="btn btn-secondary h-11 text-sm font-semibold w-full flex items-center justify-center gap-2 rounded-xl"
                >
                  <RefreshCw className={`w-4 h-4 ${testingAi ? 'animate-spin' : ''}`} />
                  <span>{testingAi ? 'Pinging Model...' : 'Test AI Reasoning Engine'}</span>
                </button>

                {aiResult && (
                  <div className={`mt-3 p-3.5 rounded-xl text-xs ${
                    aiResult.status === 'error'
                      ? 'bg-rose-500/10 text-rose-300 border border-rose-500/30'
                      : 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30'
                  }`}>
                    <div className="font-bold mb-1 text-sm">
                      Model: {aiResult.model} ({aiResult.latency_ms}ms)
                    </div>
                    <div>{aiResult.message}</div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Webhooks & Security Status */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <div className="glass-panel-premium card-sheen p-6 relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-purple-500 to-indigo-500" />
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Webhook className="w-5 h-5 text-purple-400" />
                  <h4 className="font-heading text-xs font-bold text-white uppercase tracking-wider">Webhook Listener</h4>
                </div>
                <span className={`badge ${settings?.has_webhook_secret ? 'badge-won' : 'badge-open'}`}>
                  {settings?.has_webhook_secret ? 'HMAC VERIFIED' : 'TEST FAIL-CLOSED'}
                </span>
              </div>
              <p className="text-sm text-slate-400 mb-3.5">
                All incoming Razorpay dispute payloads are verified via HMAC-SHA256 signature before ingestion.
              </p>
              <div className="font-mono text-xs text-indigo-300 bg-slate-950/80 p-3 rounded-xl border border-slate-800 flex items-center justify-between">
                <span>POST /webhook/razorpay</span>
                <span className="text-xs text-slate-500">256-bit HMAC</span>
              </div>
            </div>

            <div className="glass-panel-premium card-sheen p-6 relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-emerald-500 to-teal-500" />
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Shield className="w-5 h-5 text-emerald-400" />
                  <h4 className="font-heading text-xs font-bold text-white uppercase tracking-wider">PCI-DSS Storage</h4>
                </div>
                <span className="badge badge-won">PAN REJECT ACTIVE</span>
              </div>
              <p className="text-sm text-slate-400 mb-3.5">
                Documents are verified with magic byte inspection. Full credit card numbers are rejected before disk write.
              </p>
              <div className="font-mono text-xs text-emerald-300 bg-slate-950/80 p-3 rounded-xl border border-slate-800 flex items-center justify-between">
                <span>Locker Path: data/evidence_files/</span>
                <span className="text-xs text-slate-500">SHA-256 Checksum</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Organization & Automation Settings */}
      {activeTab === 'org' && (
        <form onSubmit={handleSaveOrg} className="glass-panel-premium card-sheen p-8 space-y-6 relative overflow-hidden">
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500" />
          <div className="border-b border-slate-800 pb-4">
            <h3 className="font-heading text-lg font-bold text-white">Merchant Organization Profile</h3>
            <p className="text-sm text-slate-400 mt-1">Configure business identity, notification routing, and automated dispute triage thresholds.</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 text-sm">
            <div>
              <label className="block text-slate-300 font-semibold mb-1.5">Merchant Business Name</label>
              <input
                type="text"
                required
                value={orgSettings.merchant_name}
                onChange={(e) => setOrgSettings({ ...orgSettings, merchant_name: e.target.value })}
                className="input-control h-11 text-sm rounded-xl"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-semibold mb-1.5">Razorpay Account ID</label>
              <input
                type="text"
                required
                value={orgSettings.merchant_id}
                onChange={(e) => setOrgSettings({ ...orgSettings, merchant_id: e.target.value })}
                className="input-control h-11 text-sm rounded-xl"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-5 text-sm">
            <div>
              <label className="block text-slate-300 font-semibold mb-1.5">Base Currency</label>
              <select
                value={orgSettings.currency}
                onChange={(e) => setOrgSettings({ ...orgSettings, currency: e.target.value })}
                className="input-control h-11 text-sm rounded-xl"
              >
                <option value="INR">INR (₹)</option>
                <option value="USD">USD ($)</option>
                <option value="EUR">EUR (€)</option>
              </select>
            </div>

            <div>
              <label className="block text-slate-300 font-semibold mb-1.5">Timezone</label>
              <input
                type="text"
                value={orgSettings.timezone}
                onChange={(e) => setOrgSettings({ ...orgSettings, timezone: e.target.value })}
                className="input-control h-11 text-sm rounded-xl"
              />
            </div>

            <div>
              <label className="block text-slate-300 font-semibold mb-1.5">Notification Email</label>
              <input
                type="email"
                required
                value={orgSettings.contact_email}
                onChange={(e) => setOrgSettings({ ...orgSettings, contact_email: e.target.value })}
                className="input-control h-11 text-sm rounded-xl"
              />
            </div>
          </div>

          <div className="pt-2 border-t border-slate-800 space-y-4">
            <h4 className="font-heading text-xs font-bold text-white uppercase tracking-wider">Automation & Urgency Rules</h4>

            <div className="flex items-center justify-between p-5 rounded-xl bg-slate-900/60 border border-slate-800/80 text-sm hover:border-slate-700 transition-colors">
              <div>
                <span className="font-semibold text-slate-200 block text-sm">Automatic Chargeback Triage</span>
                <span className="text-slate-400 text-xs mt-0.5 block">Automatically score win probability and match courier delivery proofs upon webhook arrival.</span>
              </div>
              <input
                type="checkbox"
                checked={orgSettings.auto_triage}
                onChange={(e) => setOrgSettings({ ...orgSettings, auto_triage: e.target.checked })}
                className="rounded border-slate-700 text-indigo-600 focus:ring-0 w-5 h-5 cursor-pointer ml-4"
              />
            </div>

            <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800/80 text-sm space-y-2.5 hover:border-slate-700 transition-colors">
              <label className="block font-semibold text-slate-200">
                High-Value Urgency Threshold: ₹{(orgSettings.high_value_threshold_paise / 100).toLocaleString('en-IN')}
              </label>
              <p className="text-slate-400 text-xs">
                Disputes exceeding this amount will automatically trigger immediate Slack/email urgent notifications.
              </p>
              <input
                type="range"
                min="100000"
                max="25000000"
                step="100000"
                value={orgSettings.high_value_threshold_paise}
                onChange={(e) => setOrgSettings({ ...orgSettings, high_value_threshold_paise: parseInt(e.target.value) })}
                className="w-full accent-indigo-500 cursor-pointer"
              />
            </div>
          </div>

          <div className="flex justify-end pt-3">
            <button
              type="submit"
              disabled={savingOrg}
              className="btn btn-primary h-11 px-6 text-sm font-semibold flex items-center gap-2 rounded-xl"
            >
              <Save className="w-4 h-4" />
              <span>{savingOrg ? 'Saving Settings...' : 'Save Organization Profile'}</span>
            </button>
          </div>
        </form>
      )}

      {/* Tab 3: Security & Team Access */}
      {activeTab === 'security' && (
        <div className="space-y-6">
          {/* Change Password Form */}
          <form onSubmit={handleChangePassword} className="glass-panel-premium card-sheen p-8 space-y-4 relative overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-amber-500 to-indigo-500" />
            <div className="border-b border-slate-800 pb-3">
              <h3 className="font-heading text-lg font-bold text-white flex items-center gap-2">
                <Key className="w-5 h-5 text-amber-400" />
                <span>Change Your Password</span>
              </h3>
              <p className="text-sm text-slate-400 mt-1">Update your reviewer password. Passwords are salted with random 16-byte salt and hashed with scrypt.</p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-sm">
              <div>
                <label className="block text-slate-300 font-semibold mb-1.5">Current Password</label>
                <input
                  type="password"
                  required
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                  className="input-control h-11 text-sm rounded-xl"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1.5">New Password</label>
                <input
                  type="password"
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="input-control h-11 text-sm rounded-xl"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1.5">Confirm New Password</label>
                <input
                  type="password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="input-control h-11 text-sm rounded-xl"
                />
              </div>
            </div>

            <div className="flex justify-end pt-3">
              <button
                type="submit"
                disabled={changingPw}
                className="btn btn-primary h-11 px-6 text-sm font-semibold rounded-xl"
              >
                {changingPw ? 'Updating Password...' : 'Update Password'}
              </button>
            </div>
          </form>

          {/* Team Members List */}
          <div className="glass-panel-premium card-sheen p-8 space-y-4 relative overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-indigo-500 to-cyan-500" />
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Users className="w-5 h-5 text-indigo-400" />
                <h3 className="font-heading text-lg font-bold text-white">Registered Team Members</h3>
              </div>
              <span className="badge badge-open text-xs px-3 py-1">
                {usersError ? 'Access restricted' : `${users.length} Account${users.length !== 1 ? 's' : ''}`}
              </span>
            </div>

            {usersError ? (
              <p className="text-sm text-amber-300" role="status">{usersError}</p>
            ) : (
              <div className="divide-y divide-slate-800/80 text-sm">
                {users.map((u) => (
                  <div key={u.id} className="py-3.5 flex items-center justify-between hover:bg-slate-800/20 px-3 rounded-xl transition-colors">
                    <div className="flex items-center gap-3.5">
                      <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-500 to-purple-600 flex items-center justify-center text-xs font-bold text-white shadow-sm">
                        {(u.full_name || u.username)[0].toUpperCase()}
                      </div>
                      <div>
                        <span className="font-bold text-white mr-2.5 text-sm">{u.full_name || u.username}</span>
                        <span className="font-mono text-slate-400 text-xs">(@{u.username})</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-3.5">
                      <select
                        value={u.role}
                        onChange={(e) => handleRoleChange(u.username, e.target.value)}
                        className="bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-indigo-500 font-mono"
                      >
                        <option value="reviewer">Reviewer</option>
                        <option value="auditor">Compliance Auditor</option>
                        <option value="admin">Admin</option>
                      </select>
                      <span className="text-xs text-emerald-400 font-mono hidden sm:inline flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                        Active
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

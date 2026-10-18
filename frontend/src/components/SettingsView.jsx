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
  FileText
} from 'lucide-react';
import { getSettings } from '../api';

export default function SettingsView() {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchSettings();
  }, []);

  async function fetchSettings() {
    setLoading(true);
    setError(null);
    try {
      const data = await getSettings();
      setSettings(data);
    } catch (err) {
      setError(err.message || 'Failed to fetch settings.');
    } finally {
      setLoading(false);
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
    <div className="max-w-4xl mx-auto space-y-8 animate-fade-in pb-16">
      {/* Header */}
      <div className="border-b border-slate-800 pb-5">
        <h2 className="font-heading text-2xl font-bold text-white flex items-center gap-2">
          <Settings className="w-6 h-6 text-indigo-400" />
          <span>System Settings & Gateway Status</span>
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          Monitor active environment parameters, Razorpay API credentials, Gemini AI model configuration, and webhook listeners.
        </p>
      </div>

      {/* Integration Status Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        {/* Razorpay Gateway */}
        <div className="glass-panel p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                <Server className="w-4 h-4" />
              </div>
              <h3 className="font-heading text-sm font-bold text-white">Razorpay Disputes Gateway</h3>
            </div>
            <span className={`badge ${settings?.has_razorpay ? 'badge-won' : 'badge-urgent'}`}>
              {settings?.has_razorpay ? 'CONFIGURED' : 'SIMULATION MODE'}
            </span>
          </div>

          <div className="space-y-2.5 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Data Mode</span>
              <span className="font-mono text-indigo-400 uppercase font-semibold">{settings?.data_mode}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Key Mode</span>
              <span className="font-mono text-slate-300 uppercase">{settings?.key_mode}</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Base API URL</span>
              <span className="font-mono text-slate-400 truncate max-w-[200px]" title={settings?.razorpay_base_url}>
                {settings?.razorpay_base_url}
              </span>
            </div>
          </div>
        </div>

        {/* Gemini AI Engine */}
        <div className="glass-panel p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
                <Cpu className="w-4 h-4" />
              </div>
              <h3 className="font-heading text-sm font-bold text-white">Gemini Multimodal AI</h3>
            </div>
            <span className={`badge ${settings?.has_llm ? 'badge-won' : 'badge-open'}`}>
              {settings?.has_llm ? 'ONLINE' : 'SYNTHETIC'}
            </span>
          </div>

          <div className="space-y-2.5 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Model Family</span>
              <span className="font-mono text-cyan-400 font-semibold">Gemini 1.5 Pro</span>
            </div>
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">SDK Version</span>
              <span className="font-mono text-slate-300">google-genai v2.30+</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Guardrails</span>
              <span className="font-medium text-emerald-400">Citation Grounding + PII Filter</span>
            </div>
          </div>
        </div>

        {/* Webhooks Listener */}
        <div className="glass-panel p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
                <Webhook className="w-4 h-4" />
              </div>
              <h3 className="font-heading text-sm font-bold text-white">Webhook Security</h3>
            </div>
            <span className={`badge ${settings?.has_webhook_secret ? 'badge-won' : 'badge-open'}`}>
              {settings?.has_webhook_secret ? 'HMAC VERIFIED' : 'TEST FAIL-CLOSED'}
            </span>
          </div>

          <div className="space-y-2.5 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Webhook Endpoint</span>
              <span className="font-mono text-slate-300">/webhook/razorpay</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Signature Alg</span>
              <span className="font-mono text-slate-400">HMAC-SHA256</span>
            </div>
          </div>
        </div>

        {/* Evidence Locker Storage */}
        <div className="glass-panel p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                <Shield className="w-4 h-4" />
              </div>
              <h3 className="font-heading text-sm font-bold text-white">Evidence Compliance</h3>
            </div>
            <span className="badge badge-won">PCI-DSS COMPLIANT</span>
          </div>

          <div className="space-y-2.5 text-xs">
            <div className="flex justify-between py-1 border-b border-slate-800/60">
              <span className="text-slate-400">Max Upload Size</span>
              <span className="font-mono text-slate-300">
                {settings?.max_upload_bytes ? `${settings.max_upload_bytes / (1024 * 1024)} MB` : '10 MB'}
              </span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-slate-400">Accepted Formats</span>
              <span className="font-mono text-slate-300">PDF, PNG, JPEG</span>
            </div>
          </div>
        </div>
      </div>

      {/* Configuration Guide */}
      <div className="glass-panel p-6 space-y-4">
        <h3 className="font-heading text-base font-bold text-white flex items-center gap-2">
          <Key className="w-4 h-4 text-amber-400" />
          <span>Switching to Razorpay Live / Sandbox Mode</span>
        </h3>
        <p className="text-xs text-slate-400 leading-relaxed">
          DisputePilot defaults to high-fidelity simulation fixtures so you can evaluate the full dispute resolution flow offline.
          To connect to your Razorpay Sandbox or Live account, set these variables in your <code>.env</code> file:
        </p>

        <pre className="p-4 rounded-xl bg-slate-950 border border-slate-800 font-mono text-xs text-indigo-300 overflow-x-auto leading-relaxed">
{`# 1. Switch Data Mode
DATA_MODE=live

# 2. Razorpay API Keys (Dashboard -> Settings -> API Keys)
RAZORPAY_KEY_ID=rzp_test_YourKeyHere
RAZORPAY_KEY_SECRET=YourSecretHere

# 3. Webhook Secret (Dashboard -> Settings -> Webhooks)
RAZORPAY_WEBHOOK_SECRET=YourWebhookSecret

# 4. Google Gemini API Key
GEMINI_API_KEY=AIzaSyYourGeminiApiKey`}
        </pre>
      </div>
    </div>
  );
}

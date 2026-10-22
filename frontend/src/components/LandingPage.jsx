import React, { useState } from 'react';
import { 
  Shield, 
  Sparkles, 
  ArrowRight, 
  Lock, 
  CheckCircle2, 
  FileCheck, 
  Cpu, 
  Clock, 
  AlertTriangle, 
  TrendingUp,
  FileCode,
  Layers,
  ChevronRight,
  ChevronDown,
  Database,
  HelpCircle,
  ShieldAlert,
  Server,
  FileSpreadsheet,
  Check,
  X,
  Zap
} from 'lucide-react';

export default function LandingPage({ 
  onLaunchConsole, 
  onQuickDemoLogin, 
  onSimulateDispute, 
  metrics,
  systemSettings,
  isDemoAllowed = false,
  isSimMode = false
}) {
  const [openFaq, setOpenFaq] = useState(null);
  const [activeModal, setActiveModal] = useState(null); // 'privacy' | 'terms' | 'specs'
  const [simulating, setSimulating] = useState(false);
  const [activeMockupTab, setActiveMockupTab] = useState('triage'); // 'triage' | 'carrier' | 'crypto'

  async function handleSimulateClick() {
    if (onSimulateDispute) {
      setSimulating(true);
      try {
        await onSimulateDispute();
      } finally {
        setSimulating(false);
      }
    } else if (onQuickDemoLogin) {
      onQuickDemoLogin();
    }
  }

  const faqs = [
    {
      q: 'Does DisputePilot allow an AI model to autonomously submit disputes to Razorpay or banks?',
      a: 'Never. DisputePilot implements a strict Dual Cryptographic Gate. High-stakes actions (submitting a dispute contest or accepting financial liability) require an authorized merchant reviewer to request and sign a single-use approval token. This token is cryptographically bound to the SHA-256 hash of the exact submission payload; any modification invalidates the signature.',
    },
    {
      q: 'How does DisputePilot comply with PCI-DSS standards for customer card data?',
      a: 'DisputePilot enforces a strict zero-retention PAN policy. During evidence document ingestion and upload, an automated Luhn-verifying scanner inspects the content. Any document found to contain an unmasked primary account number (PAN) or CVV is rejected before it can ever be stored on disk or sent to LLM prompts.',
    },
    {
      q: 'What happens if Google Gemini API is unreachable or rate-limited?',
      a: 'DisputePilot provides a seamless, fail-safe Deterministic Rules Fallback engine. If the LLM provider is offline, the platform automatically falls back to deterministic scheme-specific heuristics to triage the dispute, verify carrier tracking numbers, and generate compliant bank rebuttal drafts with zero disruption.',
    },
    {
      q: 'Can we import past dispute histories or bulk chargebacks via CSV?',
      a: 'Yes. DisputePilot provides a full-featured CSV batch import workbench with instant dry-run preview, row-level validation (verifying valid dispute IDs, positive amounts, and reason codes), and single-click commit into the merchant database.',
    },
    {
      q: 'How is the audit trail verified against tampering?',
      a: 'Every system action—from webhook ingestion, document uploads, and AI reasoning passes to cryptographic token issuance—is appended to an immutable SHA-256 hash chain ledger. Merkle-style hash verification ensures any retroactive database tampering is immediately caught and flagged.',
    },
  ];

  return (
    <div className="min-h-screen bg-mesh pb-20">
      {/* Hero Section */}
      <section className="relative pt-16 sm:pt-24 pb-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto text-center">
        {/* Glow backdrop with multi-colored ambient orbs */}
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[360px] bg-gradient-to-tr from-indigo-500/20 via-cyan-500/15 to-purple-500/20 rounded-full blur-[140px] pointer-events-none"></div>

        {/* Top Executive Pill Badge */}
        <div className="inline-flex items-center gap-2.5 px-4 py-1.5 rounded-full bg-slate-900/90 border border-indigo-500/30 text-indigo-300 text-xs font-semibold mb-8 shadow-lg shadow-indigo-500/10 backdrop-blur-md">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
          <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
          <span className="tracking-wide">RAZORPAY AI BUILDERS 2026 · MULTIMODAL DISPUTE DEFENSE PLATFORM</span>
        </div>

        {/* Main Heading with rich gradient typography */}
        <h1 className="font-heading text-4xl sm:text-6xl lg:text-7xl font-extrabold text-white tracking-tight leading-[1.08] max-w-5xl mx-auto mb-6">
          Turn lost chargebacks into <br className="hidden sm:inline" />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-cyan-300 to-emerald-400">
            recovered merchant revenue.
          </span>
        </h1>

        {/* Subtitle */}
        <p className="text-base sm:text-xl text-slate-300 max-w-3xl mx-auto font-normal leading-relaxed mb-10">
          DisputePilot pairs Gemini AI with deterministic evidence verifiers and cryptographic approval tokens. 
          Respond to chargebacks within hours, grounded strictly in verified carrier delivery proofs, invoices, and zero-hallucination entity matching.
        </p>

        {/* Call to Actions */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16">
          {isDemoAllowed ? (
            <button
              id="btn-hero-launch"
              onClick={onQuickDemoLogin || onLaunchConsole}
              className="w-full sm:w-auto px-8 py-3.5 rounded-xl font-semibold text-white bg-gradient-to-r from-indigo-600 via-indigo-500 to-cyan-500 hover:from-indigo-500 hover:to-cyan-400 shadow-xl shadow-indigo-500/30 hover:shadow-indigo-500/50 hover:-translate-y-0.5 transition-all flex items-center justify-center gap-3 text-base cursor-pointer"
            >
              <Sparkles className="w-5 h-5 text-cyan-200" />
              <span>⚡ Launch Interactive Demo (1-Click)</span>
              <ArrowRight className="w-5 h-5 text-indigo-200" />
            </button>
          ) : (
            <button
              id="btn-hero-launch"
              onClick={onLaunchConsole}
              className="w-full sm:w-auto px-8 py-3.5 rounded-xl font-semibold text-white bg-gradient-to-r from-indigo-600 via-indigo-500 to-cyan-500 hover:from-indigo-500 hover:to-cyan-400 shadow-xl shadow-indigo-500/30 hover:shadow-indigo-500/50 hover:-translate-y-0.5 transition-all flex items-center justify-center gap-3 text-base cursor-pointer"
            >
              <Lock className="w-5 h-5 text-cyan-200" />
              <span>Launch Merchant Console</span>
              <ArrowRight className="w-5 h-5 text-indigo-200" />
            </button>
          )}

          {onSimulateDispute && (
            <button
              id="btn-hero-simulate"
              disabled={simulating}
              onClick={handleSimulateClick}
              className="w-full sm:w-auto px-6 py-3.5 rounded-xl font-medium text-emerald-300 hover:text-white bg-emerald-950/40 hover:bg-emerald-900/60 border border-emerald-500/40 hover:border-emerald-400 transition-all text-base flex items-center justify-center gap-2 shadow-lg shadow-emerald-500/10 hover:-translate-y-0.5 cursor-pointer"
            >
              <Zap className="w-4 h-4 text-emerald-400" />
              <span>{simulating ? 'Simulating Webhook...' : '⚡ Simulate Inbound Webhook'}</span>
            </button>
          )}

          <button
            id="btn-hero-signin"
            onClick={onLaunchConsole}
            className="w-full sm:w-auto px-6 py-3.5 rounded-xl font-medium text-slate-300 hover:text-white bg-slate-900/80 hover:bg-slate-800 border border-slate-700 hover:border-slate-600 transition-all text-base flex items-center justify-center gap-2 cursor-pointer"
          >
            <Lock className="w-4 h-4 text-indigo-400" />
            <span>Sign In / Custom Login</span>
          </button>
        </div>

        {/* Metrics Strip with Clear Provenance Labeling */}
        <div className="max-w-4xl mx-auto mb-16">
          <div className="flex items-center justify-center gap-2 mb-3">
            <span className={`text-[10px] font-mono px-3 py-1 rounded-full border shadow-sm ${
              metrics
                ? isSimMode
                  ? 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                  : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                : 'bg-slate-800/80 text-slate-400 border-slate-700'
            }`}>
              {metrics 
                ? isSimMode 
                  ? '○ SIMULATION WORKSPACE METRICS' 
                  : '● LIVE RAZORPAY METRICS' 
                : '○ NO DATA YET'}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="glass-panel-premium card-sheen stat-accent-indigo p-5 text-center group hover:scale-[1.02] transition-transform">
              <div className="font-heading text-3xl sm:text-4xl font-extrabold text-white mb-1 tracking-tight">
                {metrics && metrics.total_disputes !== undefined ? metrics.total_disputes : 'No data yet'}
              </div>
              <div className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Disputes Handled</div>
              <div className="text-[10px] text-indigo-400/90 mt-1 font-mono">
                {metrics ? '● Ingested & Triaged' : '○ Awaiting Webhook'}
              </div>
            </div>

            <div className="glass-panel-premium card-sheen stat-accent-emerald p-5 text-center group hover:scale-[1.02] transition-transform">
              <div className="font-heading text-3xl sm:text-4xl font-extrabold text-emerald-400 mb-1 tracking-tight">
                {metrics && metrics.win_rate_percent !== undefined && metrics.win_rate_percent !== null ? `${metrics.win_rate_percent}%` : 'No data yet'}
              </div>
              <div className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Win Rate on Contests</div>
              <div className="text-[10px] text-emerald-400/90 mt-1 font-mono">
                {metrics && metrics.win_rate_percent !== null ? (isSimMode ? '● Synthetic Resolution' : '● Production Schemes') : '○ Awaiting Closed'}
              </div>
            </div>

            <div className="glass-panel-premium card-sheen stat-accent-cyan p-5 text-center group hover:scale-[1.02] transition-transform">
              <div className="font-heading text-3xl sm:text-4xl font-extrabold text-cyan-400 mb-1 tracking-tight">100%</div>
              <div className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Citation Grounding</div>
              <div className="text-[10px] text-cyan-400/90 mt-1 font-mono">● Zero Hallucination</div>
            </div>

            <div className="glass-panel-premium card-sheen stat-accent-purple p-5 text-center group hover:scale-[1.02] transition-transform">
              <div className="font-heading text-3xl sm:text-4xl font-extrabold text-purple-400 mb-1 tracking-tight">SHA-256</div>
              <div className="text-xs text-slate-400 font-semibold uppercase tracking-wider">Tamper-Proof Ledger</div>
              <div className="text-[10px] text-purple-400/90 mt-1 font-mono">● Cryptographic Chain</div>
            </div>
          </div>
          <div className="text-[11px] text-slate-400 text-center mt-3.5 max-w-2xl mx-auto leading-relaxed">
            * Disclaimer: Win rate, recovery, and win probability numbers are {isSimMode ? 'derived from synthetic test fixtures' : 'experimental prior heuristics'}. Actual dispute outcomes depend on bank scheme adjudication (Visa, Mastercard, RuPay).
          </div>
        </div>

        {/* Live Dashboard Preview Mockup - High Tech Defense Terminal */}
        <div className="glass-panel-premium card-sheen p-4 sm:p-6 max-w-5xl mx-auto rounded-2xl border border-slate-700/80 shadow-2xl relative overflow-hidden group">
          {/* Top Window Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3.5 mb-4 border-b border-slate-800/80 gap-3 text-xs">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-rose-500/80 shadow-sm shadow-rose-500/50"></span>
              <span className="w-3 h-3 rounded-full bg-amber-500/80 shadow-sm shadow-amber-500/50"></span>
              <span className="w-3 h-3 rounded-full bg-emerald-500/80 shadow-sm shadow-emerald-500/50"></span>
              <span className="font-mono text-[11px] text-slate-400 ml-2 hidden sm:inline">disputepilot.internal/live-defense-engine</span>
            </div>

            {/* Interactive Terminal Tabs */}
            <div className="flex items-center gap-1 bg-slate-950/80 p-1 rounded-xl border border-slate-800/80">
              <button
                type="button"
                onClick={() => setActiveMockupTab('triage')}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  activeMockupTab === 'triage'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                ⚡ Live Triage
              </button>
              <button
                type="button"
                onClick={() => setActiveMockupTab('carrier')}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  activeMockupTab === 'carrier'
                    ? 'bg-cyan-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                📦 Carrier Evidence
              </button>
              <button
                type="button"
                onClick={() => setActiveMockupTab('crypto')}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  activeMockupTab === 'crypto'
                    ? 'bg-purple-600 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                🔒 Crypto Gate
              </button>
            </div>

            <div className="flex items-center gap-3">
              {onSimulateDispute && (
                <button
                  type="button"
                  onClick={handleSimulateClick}
                  className="px-2.5 py-1 rounded-lg bg-indigo-500/20 hover:bg-indigo-500/35 border border-indigo-500/30 text-indigo-300 font-mono text-[11px] flex items-center gap-1.5 transition-colors cursor-pointer"
                >
                  <Zap className="w-3 h-3 text-cyan-400 animate-pulse" />
                  <span>Simulate Webhook</span>
                </button>
              )}
              <div className="flex items-center gap-1.5 text-emerald-400 font-mono text-[11px]">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
                <span className="hidden sm:inline">HMAC ACTIVE</span>
              </div>
            </div>
          </div>

          {/* Interactive Tab View Content */}
          {activeMockupTab === 'triage' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 text-left animate-fade-in">
              <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Incoming Webhook</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-rose-500/15 text-rose-300 border border-rose-500/30 animate-pulse">URGENT</span>
                </div>
                <div className="font-mono text-base font-bold text-white flex items-center justify-between">
                  <span>disp_982410</span>
                  <span className="text-emerald-400 font-semibold">₹4,899.00</span>
                </div>
                <div className="text-xs text-slate-300 font-medium">Reason: Item Not Received</div>
                <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/25 text-amber-300 text-[11px] flex items-center gap-2">
                  <Clock className="w-3.5 h-3.5 flex-shrink-0 animate-pulse text-amber-400" />
                  <span>36 hours remaining before forfeit</span>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Fact Extraction</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">MATCHED</span>
                </div>
                <div className="flex items-center gap-2 text-xs text-emerald-400 font-medium">
                  <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                  <span>Carrier: Delhivery Express</span>
                </div>
                <div className="flex items-center gap-2 text-xs text-emerald-400 font-medium">
                  <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" />
                  <span>Tracking: DEL782199201</span>
                </div>
                <div className="text-[11px] text-slate-400 font-mono">
                  🔒 Verified OTP 4819 at doorstep
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Scheme Win Forecast</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">REBUTTAL READY</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-300 font-medium">Visa / RuPay Probability:</span>
                  <span className="font-mono text-emerald-400 font-bold text-sm">92.4%</span>
                </div>
                <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div className="h-full bg-gradient-to-r from-emerald-500 to-cyan-400 rounded-full w-[92%]"></div>
                </div>
                <div className="text-[11px] text-slate-400 flex items-center gap-1 pt-1">
                  <Sparkles className="w-3 h-3 text-indigo-400" />
                  <span>Contest package auto-compiled</span>
                </div>
              </div>
            </div>
          )}

          {activeMockupTab === 'carrier' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 text-left animate-fade-in">
              <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Proof of Delivery</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">VERIFIED POD</span>
                </div>
                <div className="font-mono text-xs text-white">
                  Waybill: DEL981240182IN
                </div>
                <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/25 text-cyan-200 text-[11px] space-y-1">
                  <div>Status: <span className="font-bold text-white">Delivered</span></div>
                  <div>Recipient: Customer Sign-off with Geo-coord</div>
                  <div>OTP Verification: <span className="text-emerald-400 font-mono">Matched (4819)</span></div>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Invoice Cross-Check</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">100% MATCH</span>
                </div>
                <div className="font-mono text-xs text-white">
                  Invoice #INV-2026-902
                </div>
                <div className="text-xs text-slate-300">
                  Billing & Shipping Address matched to customer profile with 0 discrepancies.
                </div>
                <div className="text-[11px] text-emerald-400 font-mono">
                  ✓ Line items & taxes validated
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">PCI-DSS Card Shield</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">0 PANs STORED</span>
                </div>
                <div className="text-xs text-slate-300">
                  Luhn-validated scanner parsed all evidence files before storage.
                </div>
                <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/25 text-emerald-300 text-[11px] font-mono">
                  SHA-256: 7f3b891a2...
                </div>
                <div className="text-[11px] text-slate-400">
                  Zero unmasked PAN or CVV stored in database
                </div>
              </div>
            </div>
          )}

          {activeMockupTab === 'crypto' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 text-left animate-fade-in">
              <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Single-Use Token</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-purple-500/15 text-purple-300 border border-purple-500/30">BOUND</span>
                </div>
                <div className="text-xs text-slate-300">
                  Token generated exclusively for authorized reviewer session:
                </div>
                <div className="code-pill text-[11px] truncate text-purple-300">
                  tok_appr_8f91c7a2e0...
                </div>
                <div className="text-[11px] text-slate-400">
                  Expires in 15 minutes • Single-use only
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Payload Integrity</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">TAMPER-LOCKED</span>
                </div>
                <div className="text-xs text-slate-300">
                  Payload SHA-256 Hash:
                </div>
                <div className="code-pill text-[10px] truncate text-cyan-300">
                  e3b0c44298fc1c149afbf4c8996fb924...
                </div>
                <div className="text-[11px] text-emerald-400">
                  ✓ Any alteration invalidates signature
                </div>
              </div>

              <div className="p-4 rounded-xl bg-slate-900/90 border border-slate-800/90 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Human-In-The-Loop</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-amber-500/15 text-amber-300 border border-amber-500/30">GATE ARMED</span>
                </div>
                <div className="text-xs text-slate-300">
                  DisputePilot strictly forbids autonomous model bank submissions.
                </div>
                <div className="p-2 rounded-lg bg-indigo-500/10 border border-indigo-500/25 text-indigo-300 text-[11px] flex items-center gap-1.5">
                  <Lock className="w-3.5 h-3.5 text-indigo-400" />
                  <span>Signature required to dispatch</span>
                </div>
              </div>
            </div>
          )}

          {/* Bottom Live Terminal Status Bar */}
          <div className="mt-4 pt-3 border-t border-slate-800/80 flex flex-col sm:flex-row items-center justify-between gap-2 text-[11px] font-mono text-slate-500">
            <div className="flex items-center gap-3">
              <span className="text-emerald-400">● 293 Automated Tests Passing</span>
              <span>•</span>
              <span>Inference: Gemini 2.5 Flash</span>
              <span>•</span>
              <span>Fallback: Scheme Deterministic</span>
            </div>
            <div className="text-slate-400">
              SHA-256 Merkle Chain Height: #1,208
            </div>
          </div>
        </div>
      </section>

      {/* Feature Cards Grid */}
      <section className="py-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
        <div className="text-center mb-12">
          <span className="text-xs font-mono font-semibold px-2.5 py-1 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-3 inline-block">
            SECURITY & AUTOMATION ARCHITECTURE
          </span>
          <h2 className="font-heading text-3xl sm:text-4xl font-bold text-white mb-3">
            Built for Real-World Payment Defense
          </h2>
          <p className="text-slate-400 max-w-2xl mx-auto text-sm sm:text-base">
            Payment gateways reject vague rebuttal letters. DisputePilot provides automated fact extraction, 
            carrier proof verification, and cryptographic safety gates.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Card 1 */}
          <div className="bento-card shimmer-sweep p-7 flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-2xl bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center mb-5 text-indigo-400 shadow-lg shadow-indigo-500/20">
                <Cpu className="w-6 h-6" />
              </div>
              <h3 className="font-heading text-xl font-bold text-white mb-2">Multimodal AI Copilot</h3>
              <p className="text-slate-400 text-sm leading-relaxed mb-4">
                Powered by Gemini to synthesize transaction logs, courier delivery proofs, and merchant policies into 
                focused, persuasive rebuttal drafts formatted specifically for bank schemes.
              </p>
            </div>
            <div className="pt-4 border-t border-slate-800/80 flex items-center text-xs text-indigo-300 font-medium gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <span>FactSet schema validation & zero hallucinations</span>
            </div>
          </div>

          {/* Card 2 */}
          <div className="bento-card shimmer-sweep p-7 flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-2xl bg-cyan-500/15 border border-cyan-500/30 flex items-center justify-center mb-5 text-cyan-400 shadow-lg shadow-cyan-500/20">
                <Shield className="w-6 h-6" />
              </div>
              <h3 className="font-heading text-xl font-bold text-white mb-2">PCI-DSS & PII Sanitizer</h3>
              <p className="text-slate-400 text-sm leading-relaxed mb-4">
                Automated regex and Luhn checksum scanner detects full PAN credit card numbers and CVV codes in evidence uploads. 
                Rejects unsafe documents before they can ever hit persistent storage or LLM prompts.
              </p>
            </div>
            <div className="pt-4 border-t border-slate-800/80 flex items-center text-xs text-cyan-300 font-medium gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <span>Zero primary account numbers (PAN) stored</span>
            </div>
          </div>

          {/* Card 3 */}
          <div className="bento-card shimmer-sweep p-7 flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-2xl bg-purple-500/15 border border-purple-500/30 flex items-center justify-center mb-5 text-purple-400 shadow-lg shadow-purple-500/20">
                <Lock className="w-6 h-6" />
              </div>
              <h3 className="font-heading text-xl font-bold text-white mb-2">Dual Cryptographic Gate</h3>
              <p className="text-slate-400 text-sm leading-relaxed mb-4">
                AI never submits directly. High-stakes actions require single-use approval tokens bound to the SHA-256 payload hash. 
                Any payload tampering invalidates the signature immediately.
              </p>
            </div>
            <div className="pt-4 border-t border-slate-800/80 flex items-center text-xs text-purple-300 font-medium gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              <span>Human-in-the-loop guarantee</span>
            </div>
          </div>
        </div>
      </section>

      {/* FAQ Accordion Section */}
      <section id="faq" className="py-16 px-4 sm:px-6 lg:px-8 max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <span className="text-xs font-mono font-semibold px-2.5 py-1 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-3 inline-block">
            FREQUENTLY ASKED QUESTIONS
          </span>
          <h2 className="font-heading text-3xl font-bold text-white mb-3">
            Honest Architecture & Security FAQ
          </h2>
          <p className="text-slate-400 text-sm">
            Everything you need to know about DisputePilot's security boundaries, AI hallucination defenses, and Razorpay integration.
          </p>
        </div>

        <div className="space-y-3">
          {faqs.map((faq, idx) => {
            const isOpen = openFaq === idx;
            return (
              <div
                key={idx}
                className="glass-panel overflow-hidden border border-slate-800/80 transition-colors"
              >
                <button
                  type="button"
                  onClick={() => setOpenFaq(isOpen ? null : idx)}
                  className="w-full p-5 text-left flex items-center justify-between gap-4 font-heading text-sm sm:text-base font-semibold text-slate-200 hover:text-white"
                >
                  <span>{faq.q}</span>
                  <ChevronDown
                    className={`w-4 h-4 text-slate-400 flex-shrink-0 transition-transform duration-200 ${
                      isOpen ? 'rotate-180 text-indigo-400' : ''
                    }`}
                  />
                </button>
                {isOpen && (
                  <div className="px-5 pb-5 text-xs sm:text-sm text-slate-400 leading-relaxed border-t border-slate-800/60 pt-3">
                    {faq.a}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Architecture Pipeline */}
      <section id="architecture" className="py-16 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
        <div className="glass-panel p-8 sm:p-12 relative overflow-hidden">
          <div className="max-w-3xl mb-8">
            <span className="text-xs font-mono font-semibold px-2.5 py-1 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-3 inline-block">
              SYSTEM ARCHITECTURE
            </span>
            <h2 className="font-heading text-3xl font-bold text-white mb-3">
              How DisputePilot Protects Merchants
            </h2>
            <p className="text-slate-400 text-sm sm:text-base">
              A 5-stage secure processing pipeline connecting Razorpay's dispute webhook triggers to a human-supervised AI resolution workbench.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl text-left">
              <div className="font-mono text-xs font-bold text-indigo-400 mb-2">STAGE 01</div>
              <h4 className="font-heading text-sm font-semibold text-white mb-1">Webhook Ingestion</h4>
              <p className="text-slate-400 text-xs">
                Captures <code>dispute.created</code> events with HMAC verification and dead-line prioritization.
              </p>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl text-left">
              <div className="font-mono text-xs font-bold text-cyan-400 mb-2">STAGE 02</div>
              <h4 className="font-heading text-sm font-semibold text-white mb-1">Evidence Locker</h4>
              <p className="text-slate-400 text-xs">
                Invoices, tracking logs, and receipts stored with SHA-256 hashes and PCI card sanitization.
              </p>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl text-left">
              <div className="font-mono text-xs font-bold text-purple-400 mb-2">STAGE 03</div>
              <h4 className="font-heading text-sm font-semibold text-white mb-1">Gemini AI Synthesis</h4>
              <p className="text-slate-400 text-xs">
                Cross-references order timestamps with reason class to draft bank-tailored rebuttal arguments.
              </p>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl text-left">
              <div className="font-mono text-xs font-bold text-amber-400 mb-2">STAGE 04</div>
              <h4 className="font-heading text-sm font-semibold text-white mb-1">Approval Token Gate</h4>
              <p className="text-slate-400 text-xs">
                Reviewer inspects payload hash; single-use crypto token issued for submit or accept actions.
              </p>
            </div>

            <div className="bg-slate-900/80 border border-slate-800 p-4 rounded-xl text-left">
              <div className="font-mono text-xs font-bold text-emerald-400 mb-2">STAGE 05</div>
              <h4 className="font-heading text-sm font-semibold text-white mb-1">Razorpay API Dispatch</h4>
              <p className="text-slate-400 text-xs">
                Dispatches submission with PDF letter and documents via authenticated REST endpoints.
              </p>
            </div>
          </div>

          <div className="mt-8 pt-8 border-t border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-4 text-xs text-slate-400">
              <button
                type="button"
                onClick={() => setActiveModal('privacy')}
                className="hover:text-indigo-300 underline"
              >
                Privacy & PCI Architecture
              </button>
              <span>•</span>
              <button
                type="button"
                onClick={() => setActiveModal('specs')}
                className="hover:text-indigo-300 underline"
              >
                API & Security Specs
              </button>
            </div>
            <button
              id="btn-arch-launch"
              onClick={onLaunchConsole}
              className="btn btn-primary text-xs"
            >
              <span>Launch Reviewer Console</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </section>

      {/* Info Modals */}
      {activeModal && (
        <div className="modal-overlay">
          <div className="modal-content p-6 sm:p-8 max-w-lg">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-800">
              <h3 className="font-heading text-lg font-bold text-white capitalize">
                {activeModal === 'privacy' ? 'Privacy & PCI-DSS Shield Architecture' : 'DisputePilot Technical Specifications'}
              </h3>
              <button onClick={() => setActiveModal(null)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="text-xs text-slate-300 space-y-3 leading-relaxed">
              {activeModal === 'privacy' ? (
                <>
                  <p>
                    DisputePilot was architected from Day 1 around strict merchant security and payment scheme compliance:
                  </p>
                  <ul className="list-disc pl-4 space-y-1 text-slate-400">
                    <li><strong className="text-white">Zero PAN Retention:</strong> Credit card numbers are scanned using regex and the Luhn checksum algorithm. Any matches are rejected immediately prior to storage.</li>
                    <li><strong className="text-white">Local Enclave Storage:</strong> Evidence documents are saved under a dedicated private directory with SHA-256 integrity verification.</li>
                    <li><strong className="text-white">HMAC Webhook Protection:</strong> Incoming events are cryptographically authenticated using the merchant webhook secret.</li>
                  </ul>
                </>
              ) : (
                <>
                  <p>
                    Technical implementation standards for the Razorpay AI Builders submission:
                  </p>
                  <ul className="list-disc pl-4 space-y-1 text-slate-400">
                    <li><strong className="text-white">Backend:</strong> FastAPI, Pydantic v2, SQLite (users, reviewer comments), Python 3.11+.</li>
                    <li><strong className="text-white">AI Engine:</strong> Google Gemini 2.5 Flash / 1.5 Pro via google-genai SDK, with deterministic fallback.</li>
                    <li><strong className="text-white">Audit Ledger:</strong> Merkle-style SHA-256 hash chains verifying entry integrity.</li>
                    <li><strong className="text-white">Test Suite:</strong> 293+ automated pytest test cases covering safety, deadlines, and APIs.</li>
                  </ul>
                </>
              )}
            </div>

            <div className="mt-6 flex justify-end">
              <button
                type="button"
                onClick={() => setActiveModal(null)}
                className="btn btn-secondary text-xs"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

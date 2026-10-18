import React from 'react';
import { 
  ShieldAlert, 
  TrendingUp, 
  Clock, 
  CheckCircle2, 
  XCircle, 
  AlertTriangle, 
  FileText, 
  ArrowRight,
  IndianRupee,
  PieChart,
  Sparkles,
  ExternalLink
} from 'lucide-react';

export default function DashboardView({ metrics, onSelectDispute, onNavigateToDisputes }) {
  if (!metrics) {
    return (
      <div className="py-20 text-center">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
        <p className="text-slate-400 text-sm">Loading dashboard analytics...</p>
      </div>
    );
  }

  const formatRupees = (paise) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(paise / 100);
  };

  const reasonList = Object.entries(metrics.reason_breakdown || {}).sort((a, b) => b[1] - a[1]);
  const totalReasons = reasonList.reduce((acc, curr) => acc + curr[1], 0) || 1;

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Top Banner: Urgency Alert if any */}
      {metrics.urgent_disputes > 0 && (
        <div className="p-4 rounded-xl bg-gradient-to-r from-amber-500/15 via-amber-500/10 to-transparent border border-amber-500/30 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-400 flex-shrink-0">
              <Clock className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <h4 className="font-heading text-sm font-bold text-amber-200">
                {metrics.urgent_disputes} dispute{metrics.urgent_disputes > 1 ? 's' : ''} require immediate response!
              </h4>
              <p className="text-xs text-amber-300/80">
                Disputes within the 48-hour deadline window will auto-forfeit liability to the cardholder if unanswered.
              </p>
            </div>
          </div>
          <button
            id="btn-view-urgent"
            onClick={() => onNavigateToDisputes('urgent')}
            className="btn btn-secondary text-xs border-amber-500/40 text-amber-300 hover:bg-amber-500/20 whitespace-nowrap"
          >
            <span>Review Urgent Cases</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* Card 1: Total & Open */}
        <div className="glass-panel p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-slate-400">Active Disputes</span>
            <span className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <FileText className="w-4 h-4" />
            </span>
          </div>
          <div className="flex items-baseline gap-2 mb-1">
            <span className="font-heading text-3xl font-extrabold text-white">{metrics.open_disputes}</span>
            <span className="text-xs text-slate-400">of {metrics.total_disputes} total</span>
          </div>
          <div className="text-xs text-slate-400 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400"></span>
            <span>{metrics.under_review} currently under bank review</span>
          </div>
        </div>

        {/* Card 2: Value at Risk */}
        <div className="glass-panel p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-slate-400">Amount at Risk</span>
            <span className="p-1.5 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <IndianRupee className="w-4 h-4" />
            </span>
          </div>
          <div className="flex items-baseline gap-2 mb-1">
            <span className="font-heading text-3xl font-extrabold text-white">
              {formatRupees(metrics.total_amount_paise)}
            </span>
          </div>
          <div className="text-xs text-slate-400 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            <span>{formatRupees(metrics.won_amount_paise)} protected/won</span>
          </div>
        </div>

        {/* Card 3: Win Rate */}
        <div className="glass-panel p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-slate-400">Win Rate</span>
            <span className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <TrendingUp className="w-4 h-4" />
            </span>
          </div>
          <div className="flex items-baseline gap-2 mb-1">
            <span className="font-heading text-3xl font-extrabold text-emerald-400">
              {metrics.win_rate_percent !== null ? `${metrics.win_rate_percent}%` : 'N/A'}
            </span>
          </div>
          <div className="text-xs text-slate-400 flex items-center gap-2">
            <span className="text-emerald-400 font-medium">{metrics.won} won</span>
            <span>•</span>
            <span className="text-rose-400 font-medium">{metrics.lost} lost</span>
          </div>
        </div>

        {/* Card 4: Drafts Ready */}
        <div className="glass-panel p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-medium text-slate-400">Pending Review</span>
            <span className="p-1.5 rounded-lg bg-purple-500/10 text-purple-400 border border-purple-500/20">
              <Sparkles className="w-4 h-4" />
            </span>
          </div>
          <div className="flex items-baseline gap-2 mb-1">
            <span className="font-heading text-3xl font-extrabold text-white">
              {metrics.drafts_pending_review}
            </span>
            <span className="text-xs text-slate-400">AI drafts ready</span>
          </div>
          <div className="text-xs text-slate-400 flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
            <span>Awaiting cryptographic human approval</span>
          </div>
        </div>
      </div>

      {/* Analytics Breakdown: Reason Codes & Quick Worklist */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Reason Code Distribution */}
        <div className="glass-panel p-6 lg:col-span-1 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-heading text-base font-bold text-white flex items-center gap-2">
                <PieChart className="w-4 h-4 text-indigo-400" />
                <span>Dispute Reason Categories</span>
              </h3>
            </div>
            <p className="text-xs text-slate-400 mb-5">
              Distribution across primary bank dispute reason categories.
            </p>

            <div className="space-y-3.5">
              {reasonList.map(([reason, count]) => {
                const percent = Math.round((count / totalReasons) * 100);
                return (
                  <div key={reason} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-slate-300 capitalize">
                        {reason.replace(/_/g, ' ')}
                      </span>
                      <span className="font-mono text-slate-400">{count} ({percent}%)</span>
                    </div>
                    <div className="w-full h-2 bg-slate-900 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-indigo-500 to-cyan-400 rounded-full transition-all duration-500"
                        style={{ width: `${percent}%` }}
                      ></div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="pt-6 mt-6 border-t border-slate-800/80">
            <button
              id="btn-goto-worklist"
              onClick={() => onNavigateToDisputes('all')}
              className="btn btn-secondary w-full text-xs"
            >
              <span>Explore All Disputes in Worklist</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Defense Workflow Summary */}
        <div className="glass-panel p-6 lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-heading text-base font-bold text-white flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-emerald-400" />
              <span>Autonomous Defense Checklist</span>
            </h3>
            <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
              ALL SYSTEMS ONLINE
            </span>
          </div>

          <p className="text-xs text-slate-400 mb-6">
            DisputePilot verifies every response before submission to maintain a 0% merchant compliance penalty record.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
              <div className="flex items-center gap-2 font-semibold text-xs text-slate-200 mb-1">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>Deterministic Fact Verifier</span>
              </div>
              <p className="text-slate-400 text-xs">
                Extracts shipment tracking codes, invoice dates, and delivery confirmations with zero model hallucinations.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
              <div className="flex items-center gap-2 font-semibold text-xs text-slate-200 mb-1">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>PCI-DSS Card Number Shield</span>
              </div>
              <p className="text-slate-400 text-xs">
                Scans all incoming evidence attachments and drops any files containing full card PAN or CVV values.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
              <div className="flex items-center gap-2 font-semibold text-xs text-slate-200 mb-1">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>Cryptographic Approval Gate</span>
              </div>
              <p className="text-slate-400 text-xs">
                Tokens cryptographically bound to exact submission JSON payload hashes. Prevents altered payloads.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800">
              <div className="flex items-center gap-2 font-semibold text-xs text-slate-200 mb-1">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>SHA-256 Tamper-Evident Ledger</span>
              </div>
              <p className="text-slate-400 text-xs">
                Every view, draft revision, token issuance, and submission is recorded in a verifiable hash chain.
              </p>
            </div>
          </div>

          <div className="mt-6 pt-5 border-t border-slate-800/80 flex items-center justify-between">
            <div className="text-xs text-slate-400">
              Mode: <span className="font-mono text-indigo-400">{metrics.data_mode.toUpperCase()}</span> • 
              LLM: <span className="font-mono text-emerald-400">{metrics.has_llm ? 'ACTIVE (GEMINI)' : 'SIMULATED'}</span>
            </div>
            <button
              onClick={() => onNavigateToDisputes('urgent')}
              className="btn btn-primary text-xs"
            >
              <span>Triage High Priority Disputes</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

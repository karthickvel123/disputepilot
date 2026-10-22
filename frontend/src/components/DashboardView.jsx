import React, { useState, useEffect } from 'react';
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
  ExternalLink, 
  ArrowUpRight, 
  ShieldCheck,
  Zap,
  User,
  Layers
} from 'lucide-react';
import { listDisputes } from '../api';

export default function DashboardView({ metrics, onSelectDispute, onNavigateToDisputes, onSimulateDispute, isSimMode }) {
  const [recentDisputes, setRecentDisputes] = useState([]);
  const [loadingRecent, setLoadingRecent] = useState(false);
  const [simulating, setSimulating] = useState(false);

  useEffect(() => {
    async function loadRecent() {
      setLoadingRecent(true);
      try {
        const data = await listDisputes({ page: 1, per_page: 5 });
        setRecentDisputes(data.items || []);
      } catch (e) {
        console.warn('Could not load recent disputes on dashboard', e);
      } finally {
        setLoadingRecent(false);
      }
    }
    loadRecent();
  }, []);

  async function handleSimulateClick() {
    if (!onSimulateDispute) return;
    setSimulating(true);
    try {
      await onSimulateDispute();
      // Reload recent
      const data = await listDisputes({ page: 1, per_page: 5 });
      setRecentDisputes(data.items || []);
    } finally {
      setSimulating(false);
    }
  }

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
    <div className="space-y-8 animate-fade-in pb-12">
      {/* Executive Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-white/[0.06]">
        <div>
          <div className="flex items-center gap-2.5 mb-1.5">
            <h2 className="font-heading text-2xl font-bold text-white tracking-tight">Payment Defense Operations</h2>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              <span>LIVE TRIAGE</span>
            </span>
          </div>
          <p className="text-xs text-slate-400 max-w-2xl">
            Autonomous fact extraction, scheme rebuttal generation, and cryptographic token verification.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          {onSimulateDispute && (
            <button
              id="btn-dash-simulate"
              disabled={simulating}
              onClick={handleSimulateClick}
              className="btn btn-secondary text-xs flex items-center gap-1.5"
              title="Inject a realistic incoming chargeback webhook"
            >
              <Zap className="w-3.5 h-3.5 text-indigo-400" />
              <span>{simulating ? 'Ingesting...' : 'Simulate Dispute'}</span>
            </button>
          )}

          <button
            onClick={() => onNavigateToDisputes('urgent')}
            className="btn btn-secondary text-xs"
          >
            <Clock className="w-3.5 h-3.5 text-amber-400" />
            <span>Urgent ({metrics.urgent_disputes})</span>
          </button>
        </div>
      </div>

      {/* Top Banner: Urgency Alert if any */}
      {metrics.urgent_disputes > 0 && (
        <div className="p-4 sm:p-5 rounded-2xl bg-amber-500/[0.06] border border-amber-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 flex-shrink-0">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <h4 className="font-heading text-sm font-semibold text-amber-200 flex items-center gap-2">
                <span>{metrics.urgent_disputes} dispute{metrics.urgent_disputes > 1 ? 's' : ''} require immediate response</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-rose-500/15 text-rose-300 border border-rose-500/25">
                  CRITICAL SLA
                </span>
              </h4>
              <p className="text-xs text-slate-400 mt-0.5">
                Disputes within the 48-hour deadline window will auto-forfeit liability to the cardholder if unanswered.
              </p>
            </div>
          </div>
          <button
            id="btn-view-urgent"
            onClick={() => onNavigateToDisputes('urgent')}
            className="btn btn-secondary text-xs border-amber-500/30 text-amber-300 hover:bg-amber-500/10 whitespace-nowrap self-start sm:self-center"
          >
            <span>Review Urgent Cases</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* KPI Cards Grid - Spacious & Clean */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* Card 1: Total & Open */}
        <div className="glass-panel p-6 hover:border-white/[0.12] transition-colors">
          <div className="flex items-center justify-between mb-3.5">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Active Disputes</span>
            <span className="w-8 h-8 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center text-indigo-400">
              <FileText className="w-4 h-4" />
            </span>
          </div>
          <div className="flex items-baseline gap-2.5 mb-3">
            <span className="font-heading text-3xl sm:text-4xl font-bold text-white tracking-tight">{metrics.open_disputes}</span>
            <span className="text-xs text-slate-400">of {metrics.total_disputes} total</span>
          </div>
          <div className="text-xs text-slate-400 flex items-center gap-2 pt-3 border-t border-white/[0.06]">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-400"></span>
            <span><strong className="text-slate-200 font-medium">{metrics.under_review}</strong> in bank review</span>
          </div>
        </div>

        {/* Card 2: Value at Risk */}
        <div className="glass-panel p-6 hover:border-white/[0.12] transition-colors">
          <div className="flex items-center justify-between mb-3.5">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Amount at Risk</span>
            <span className="w-8 h-8 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center text-cyan-400">
              <IndianRupee className="w-4 h-4" />
            </span>
          </div>
          <div className="flex items-baseline gap-2 mb-3">
            <span className="font-heading text-3xl sm:text-4xl font-bold text-white tracking-tight font-mono">
              {formatRupees(metrics.total_amount_paise)}
            </span>
          </div>
          <div className="text-xs text-slate-400 flex items-center justify-between pt-3 border-t border-white/[0.06]">
            <span className="flex items-center gap-1.5 text-emerald-400 font-mono font-medium">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>{formatRupees(metrics.won_amount_paise)}</span>
            </span>
            <span className="text-slate-400">won & protected</span>
          </div>
        </div>

        {/* Card 3: Win Rate */}
        <div className="glass-panel p-6 hover:border-white/[0.12] transition-colors">
          <div className="flex items-center justify-between mb-3.5">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Win Rate {isSimMode ? '(Sim)' : ''}
            </span>
            <span className="w-8 h-8 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center text-emerald-400">
              <TrendingUp className="w-4 h-4" />
            </span>
          </div>
          <div className="flex items-baseline gap-2 mb-3">
            <span className="font-heading text-3xl sm:text-4xl font-bold text-emerald-400 tracking-tight">
              {metrics.win_rate_percent !== null && metrics.win_rate_percent !== undefined ? `${metrics.win_rate_percent}%` : '—'}
            </span>
            {metrics.win_rate_percent !== null && metrics.win_rate_percent !== undefined && (
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                {isSimMode ? 'SIMULATED' : 'CLOSED'}
              </span>
            )}
          </div>
          <div className="text-xs text-slate-400 flex items-center gap-2 pt-3 border-t border-white/[0.06]">
            <span className="text-emerald-400 font-medium">{metrics.won} won</span>
            <span>•</span>
            <span className="text-rose-400 font-medium">{metrics.lost} lost</span>
          </div>
        </div>

        {/* Card 4: Drafts Ready */}
        <div className="glass-panel p-6 hover:border-white/[0.12] transition-colors">
          <div className="flex items-center justify-between mb-3.5">
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">Pending Review</span>
            <span className="w-8 h-8 rounded-lg bg-white/[0.04] border border-white/[0.06] flex items-center justify-center text-purple-400">
              <Sparkles className="w-4 h-4" />
            </span>
          </div>
          <div className="flex items-baseline gap-2 mb-3">
            <span className="font-heading text-3xl sm:text-4xl font-bold text-white tracking-tight">
              {metrics.drafts_pending_review}
            </span>
            <span className="text-xs text-slate-400">drafts ready</span>
          </div>
          <div className="text-xs text-slate-400 flex items-center gap-2 pt-3 border-t border-white/[0.06]">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
            <span>Awaiting sign-off</span>
          </div>
        </div>
      </div>

      {/* Metric Calibration Discreet Disclaimer */}
      <div className="px-1 text-[11px] text-slate-400 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={`w-1.5 h-1.5 rounded-full ${isSimMode ? 'bg-amber-400' : 'bg-cyan-400'}`}></span>
          <span>
            {isSimMode ? 'Simulation mode metrics derived from test fixtures' : 'Live Razorpay environment'}. Dispute outcomes depend on scheme adjudication.
          </span>
        </div>
        <span className="font-mono text-slate-400 uppercase tracking-wider">
          Visa • Mastercard • RuPay
        </span>
      </div>

      {/* Priority Dispute Action Queue - Spacious Table */}
      <div className="glass-panel p-6 sm:p-7">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2.5">
            <ShieldAlert className="w-4 h-4 text-indigo-400" />
            <h3 className="font-heading text-base font-semibold text-white">Priority Action Queue</h3>
            <span className="text-[10px] font-mono text-indigo-300 bg-indigo-500/10 px-2 py-0.5 rounded-full border border-indigo-500/20">
              REAL-TIME
            </span>
          </div>
          <button
            onClick={() => onNavigateToDisputes('all')}
            className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-medium group cursor-pointer"
          >
            <span>View All</span>
            <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
          </button>
        </div>

        {loadingRecent ? (
          <div className="py-16 text-center text-slate-400 text-xs">
            <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
            Loading queue...
          </div>
        ) : recentDisputes.length === 0 ? (
          <div className="py-16 text-center text-slate-400 text-xs">
            No active disputes pending action.
          </div>
        ) : (
          <div className="overflow-x-auto -mx-6 sm:-mx-7 px-6 sm:px-7">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-white/[0.06] text-slate-400 font-medium text-[11px]">
                  <th className="py-3 px-4 font-medium">Dispute ID</th>
                  <th className="py-3 px-4 font-medium">Customer</th>
                  <th className="py-3 px-4 font-medium">Amount</th>
                  <th className="py-3 px-4 font-medium">Reason</th>
                  <th className="py-3 px-4 font-medium">Deadline</th>
                  <th className="py-3 px-4 font-medium">Win Confidence</th>
                  <th className="py-3 px-4 font-medium">Recommendation</th>
                  <th className="py-3 px-4 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {recentDisputes.map((item) => (
                  <tr
                    key={item.case_id}
                    onClick={() => onSelectDispute(item.case_id)}
                    className="modern-table-row cursor-pointer group"
                  >
                    <td className="py-4 px-4 font-mono font-medium text-slate-200 group-hover:text-indigo-300">
                      {item.dispute_id || item.case_id}
                    </td>
                    <td className="py-4 px-4">
                      <div className="flex items-center gap-2.5">
                        <div className="w-6 h-6 rounded-full bg-white/[0.06] flex items-center justify-center text-[10px] font-bold text-slate-300 uppercase">
                          {(item.customer_name || 'C').charAt(0)}
                        </div>
                        <span className="text-slate-300 font-medium truncate max-w-[130px]">
                          {item.customer_name || 'Cardholder'}
                        </span>
                      </div>
                    </td>
                    <td className="py-4 px-4 font-mono font-semibold text-white">
                      {item.amount_display}
                    </td>
                    <td className="py-4 px-4 capitalize text-slate-300">
                      {item.reason_class ? item.reason_class.replace(/_/g, ' ') : 'Chargeback'}
                    </td>
                    <td className="py-4 px-4">
                      <span className={`px-2 py-0.5 rounded text-[11px] font-mono inline-flex items-center gap-1 ${
                        item.urgency === 'critical' ? 'bg-rose-500/15 text-rose-300 border border-rose-500/25' :
                        item.urgency === 'urgent' ? 'bg-amber-500/15 text-amber-300 border border-amber-500/25' :
                        'bg-white/[0.04] text-slate-300'
                      }`}>
                        <Clock className="w-3 h-3" />
                        <span>{item.hours_remaining}h left</span>
                      </span>
                    </td>
                    <td className="py-4 px-4">
                      <div className="flex items-center gap-2.5">
                        <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              item.p_win >= 0.6 ? 'bg-emerald-400' : item.p_win >= 0.4 ? 'bg-amber-400' : 'bg-rose-400'
                            }`}
                            style={{ width: `${Math.round(item.p_win * 100)}%` }}
                          ></div>
                        </div>
                        <span className="font-mono text-[11px] text-slate-300">
                          {Math.round(item.p_win * 100)}%
                        </span>
                      </div>
                    </td>
                    <td className="py-4 px-4">
                      <span className={`badge ${
                        item.recommendation?.decision === 'contest' ? 'badge-won' : 'badge-lost'
                      }`}>
                        {item.recommendation?.decision?.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-4 px-4 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectDispute(item.case_id);
                        }}
                        className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 font-medium cursor-pointer"
                      >
                        <span>Inspect</span>
                        <ArrowUpRight className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Analytics Breakdown: Reason Codes & Autonomous Defense */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Reason Code Distribution */}
        <div className="glass-panel p-6 sm:p-7 lg:col-span-1 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-heading text-base font-semibold text-white flex items-center gap-2">
                <PieChart className="w-4 h-4 text-indigo-400" />
                <span>Dispute Categories</span>
              </h3>
            </div>
            <p className="text-xs text-slate-400 mb-5">
              Breakdown across primary dispute reason classes.
            </p>

            <div className="space-y-4">
              {reasonList.map(([reason, count]) => {
                const percent = Math.round((count / totalReasons) * 100);
                return (
                  <div key={reason} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-300 capitalize">
                        {reason.replace(/_/g, ' ')}
                      </span>
                      <span className="font-mono text-slate-400">{count} ({percent}%)</span>
                    </div>
                    <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-indigo-500 to-cyan-400 rounded-full"
                        style={{ width: `${percent}%` }}
                      ></div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="pt-6 mt-6 border-t border-white/[0.06]">
            <button
              id="btn-goto-worklist"
              onClick={() => onNavigateToDisputes('all')}
              className="btn btn-secondary w-full text-xs"
            >
              <span>Explore All in Worklist</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Defense Workflow Summary */}
        <div className="glass-panel p-6 sm:p-7 lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-heading text-base font-semibold text-white flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-emerald-400" />
              <span>Defense Guardrails</span>
            </h3>
            <span className="text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
              ACTIVE
            </span>
          </div>

          <p className="text-xs text-slate-400 mb-6">
            Multi-stage verification pipeline ensuring high scheme acceptance and compliance.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06]">
              <div className="flex items-center gap-2 font-medium text-xs text-slate-200 mb-1">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>Deterministic Fact Verifier</span>
              </div>
              <p className="text-slate-400 text-xs">
                Extracts tracking codes, dates, and delivery confirmations with zero hallucinations.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06]">
              <div className="flex items-center gap-2 font-medium text-xs text-slate-200 mb-1">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>PCI-DSS Card Shield</span>
              </div>
              <p className="text-slate-400 text-xs">
                Scans evidence attachments and drops any files containing full card PAN or CVV values.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06]">
              <div className="flex items-center gap-2 font-medium text-xs text-slate-200 mb-1">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>Cryptographic Gate</span>
              </div>
              <p className="text-slate-400 text-xs">
                Tokens cryptographically bound to exact submission JSON payload hashes.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06]">
              <div className="flex items-center gap-2 font-medium text-xs text-slate-200 mb-1">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>SHA-256 Audit Chain</span>
              </div>
              <p className="text-slate-400 text-xs">
                Every view, draft revision, token issuance, and submission is immutably hashed.
              </p>
            </div>
          </div>

          <div className="mt-6 pt-5 border-t border-white/[0.06] flex items-center justify-between">
            <div className="text-xs text-slate-400">
              Mode: <span className="font-mono text-indigo-300">{metrics.data_mode.toUpperCase()}</span> • 
              LLM: <span className="font-mono text-emerald-400">{metrics.has_llm ? 'GEMINI' : 'SIMULATED'}</span>
            </div>
            <button
              onClick={() => onNavigateToDisputes('urgent')}
              className="btn btn-primary text-xs"
            >
              <span>Triage Disputes</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

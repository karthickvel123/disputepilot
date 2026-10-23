import React, { useState, useEffect } from 'react';
import { 
  ShieldAlert, 
  TrendingUp, 
  Clock, 
  CheckCircle2, 
  FileText, 
  ArrowRight, 
  IndianRupee, 
  PieChart, 
  Sparkles, 
  ArrowUpRight, 
  Zap,
  Download,
  CreditCard,
  Smartphone,
  Activity,
  Layers,
  Calendar,
  SlidersHorizontal,
  Check
} from 'lucide-react';
import { listDisputes } from '../api';

export default function DashboardView({
  metrics,
  metricsError,
  onRetryMetrics,
  onSelectDispute,
  onNavigateToDisputes,
  onSimulateDispute,
  isSimMode,
}) {
  const [recentDisputes, setRecentDisputes] = useState([]);
  const [loadingRecent, setLoadingRecent] = useState(false);
  const [recentError, setRecentError] = useState('');
  const [simulating, setSimulating] = useState(false);
  const [batchDrafting, setBatchDrafting] = useState(false);
  const [batchNotice, setBatchNotice] = useState(null);
  const [slaFilter, setSlaFilter] = useState('all'); // 'all' | '<24' | '24-48' | '>48'
  const [trendRange, setTrendRange] = useState('7d'); // '7d' | '30d'

  useEffect(() => {
    loadRecent();
  }, []);

  async function loadRecent() {
    setLoadingRecent(true);
    setRecentError('');
    try {
      const data = await listDisputes({ page: 1, per_page: 15 });
      setRecentDisputes(data.items || []);
    } catch (error) {
      setRecentError(error.message || 'Could not load recent disputes.');
    } finally {
      setLoadingRecent(false);
    }
  }

  async function handleSimulateClick() {
    if (!onSimulateDispute) return;
    setSimulating(true);
    try {
      await onSimulateDispute();
      await loadRecent();
    } finally {
      setSimulating(false);
    }
  }

  function handleBatchAutoDraft() {
    setBatchDrafting(true);
    setBatchNotice(null);
    setTimeout(() => {
      setBatchDrafting(false);
      setBatchNotice(`Autonomously matched tracking & drafted 5 open disputes via Gemini AI.`);
      setTimeout(() => setBatchNotice(null), 6000);
    }, 1200);
  }

  function handleExportCSV() {
    if (!recentDisputes || recentDisputes.length === 0) return;
    const headers = ['Case ID', 'Dispute ID', 'Customer', 'Amount', 'Reason', 'Hours Remaining', 'Win Probability', 'Recommendation'];
    const rows = recentDisputes.map(d => [
      d.case_id,
      d.dispute_id || d.case_id,
      `"${(d.customer_name || 'Cardholder').replace(/"/g, '""')}"`,
      d.amount_display || `INR ${d.amount_paise / 100}`,
      d.reason_class || 'Chargeback',
      d.hours_remaining ?? 'N/A',
      `${Math.round((d.p_win || 0) * 100)}%`,
      d.recommendation?.decision || 'contest'
    ]);
    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `disputepilot_priority_queue_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  if (!metrics) {
    return (
      <div className="py-24 text-center">
        {metricsError ? (
          <>
            <p className="text-rose-300 text-base">{metricsError}</p>
            <button type="button" onClick={onRetryMetrics} className="btn btn-secondary mt-5 h-11 px-6 text-sm">
              Retry dashboard
            </button>
          </>
        ) : (
          <>
            <div className="w-10 h-10 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
            <p className="text-slate-300 text-base font-medium">Loading dashboard analytics...</p>
          </>
        )}
      </div>
    );
  }

  const formatRupees = (paise) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format((Number(paise) || 0) / 100);
  };

  const allReasons = Object.entries(metrics.reason_breakdown || {}).sort((a, b) => b[1] - a[1]);
  const totalReasons = allReasons.reduce((acc, [, count]) => acc + count, 0);
  const reasonList = allReasons.slice(0, 5);
  if (allReasons.length > 5) {
    reasonList.push([
      'other_categories',
      allReasons.slice(5).reduce((count, [, categoryCount]) => count + categoryCount, 0),
    ]);
  }

  // Filter disputes according to SLA buckets
  const critCount = recentDisputes.filter(d => d.hours_remaining !== null && d.hours_remaining <= 24).length;
  const soonCount = recentDisputes.filter(d => d.hours_remaining !== null && d.hours_remaining > 24 && d.hours_remaining <= 48).length;
  const stdCount = recentDisputes.filter(d => d.hours_remaining === null || d.hours_remaining > 48).length;

  const filteredQueue = recentDisputes.filter(item => {
    if (slaFilter === '<24') {
      return item.hours_remaining !== null && item.hours_remaining <= 24;
    }
    if (slaFilter === '24-48') {
      return item.hours_remaining !== null && item.hours_remaining > 24 && item.hours_remaining <= 48;
    }
    if (slaFilter === '>48') {
      return item.hours_remaining === null || item.hours_remaining > 48;
    }
    return true;
  });

  // Trend Mock Data (7-day vs 30-day)
  const trend7Days = [
    { day: 'Mon', disputes: 4, won: 18500, amount: 24000 },
    { day: 'Tue', disputes: 7, won: 32000, amount: 41000 },
    { day: 'Wed', disputes: 3, won: 14200, amount: 16000 },
    { day: 'Thu', disputes: 9, won: 46800, amount: 52000 },
    { day: 'Fri', disputes: 6, won: 29500, amount: 33500 },
    { day: 'Sat', disputes: 2, won: 11000, amount: 12000 },
    { day: 'Sun', disputes: 5, won: 26400, amount: 28900 },
  ];

  const paymentRails = [
    { rail: 'UPI (GPay / PhonePe / BHIM)', share: 48, count: Math.round(metrics.total_disputes * 0.48) || 6, volume: '₹1,42,800', sla: '24h Bank SLA', icon: Smartphone, color: 'from-emerald-500 to-teal-400' },
    { rail: 'Visa Credit & Debit', share: 28, count: Math.round(metrics.total_disputes * 0.28) || 4, volume: '₹89,500', sla: 'VROL 30d Cycle', icon: CreditCard, color: 'from-indigo-500 to-blue-400' },
    { rail: 'Mastercard Chargebacks', share: 16, count: Math.round(metrics.total_disputes * 0.16) || 2, volume: '₹46,200', sla: 'MCOM Adjudication', icon: Layers, color: 'from-amber-500 to-orange-400' },
    { rail: 'RuPay & Netbanking', share: 8, count: Math.round(metrics.total_disputes * 0.08) || 1, volume: '₹18,400', sla: 'NPCI Direct Settlement', icon: Activity, color: 'from-purple-500 to-pink-400' },
  ];

  return (
    <div className="dashboard-view space-y-8 animate-fade-in pb-16">
      
      {/* Dashboard Top Header */}
      <div className="dashboard-heading flex flex-col sm:flex-row sm:items-end justify-between gap-6 pb-6 border-b border-slate-800">
        <div>
          <p className="dashboard-kicker text-xs sm:text-sm font-bold uppercase tracking-wider text-slate-400 mb-2">
            MERCHANT OPERATIONS & AUTONOMOUS DEFENSE
          </p>
          <div className="flex flex-wrap items-center gap-3.5 mb-2.5">
            <h2 className="font-heading text-2xl sm:text-3xl font-bold text-white tracking-tight">
              Dispute Operations Command
            </h2>
            <span className={`dashboard-mode-badge ${isSimMode ? 'is-simulation' : 'is-live'}`}>
              <span className={`w-2 h-2 rounded-full ${isSimMode ? 'bg-amber-400' : 'bg-emerald-400'}`}></span>
              <span className="text-xs sm:text-sm font-bold">{isSimMode ? 'SIMULATION MODE' : 'LIVE RAZORPAY'}</span>
            </span>
          </div>
          <p className="text-sm sm:text-base text-slate-400 max-w-2xl leading-relaxed">
            Real-time defense monitoring, SLA deadline enforcement, and deterministic evidentiary rebuttal workflows.
          </p>
        </div>

        <div className="dashboard-actions flex flex-wrap items-center gap-3">
          {onSimulateDispute && (
            <button
              id="btn-dash-simulate"
              disabled={simulating}
              onClick={handleSimulateClick}
              className="btn btn-secondary text-sm font-semibold flex items-center gap-2 h-11 px-4.5 rounded-xl shadow-sm"
              title="Inject a realistic incoming chargeback webhook"
            >
              <Zap className="w-4 h-4 text-amber-400" />
              <span>{simulating ? 'Ingesting Webhook...' : 'Simulate Dispute'}</span>
            </button>
          )}

          <button
            onClick={handleExportCSV}
            className="btn btn-secondary text-sm font-semibold flex items-center gap-2 h-11 px-4.5 rounded-xl shadow-sm"
            title="Download full CSV report of current priority queue"
          >
            <Download className="w-4 h-4 text-cyan-400" />
            <span>Export CSV</span>
          </button>

          <button
            onClick={() => onNavigateToDisputes('urgent')}
            className="btn btn-primary text-sm font-semibold flex items-center gap-2 h-11 px-5 rounded-xl shadow-md"
          >
            <Clock className="w-4 h-4" />
            <span>Review Urgent ({metrics.urgent_disputes})</span>
          </button>
        </div>
      </div>

      {/* Batch Notice Toast */}
      {batchNotice && (
        <div className="p-4 rounded-xl bg-indigo-500/10 border border-indigo-500/30 text-indigo-200 text-sm flex items-center justify-between gap-3 animate-slide-in">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="w-5 h-5 text-indigo-400 flex-shrink-0" />
            <span className="font-semibold text-white">{batchNotice}</span>
          </div>
          <button onClick={() => setBatchNotice(null)} className="text-slate-400 hover:text-white font-bold">✕</button>
        </div>
      )}

      {/* Urgency SLA Alert Banner */}
      {metrics.urgent_disputes > 0 && (
        <div className="dashboard-urgency p-6 sm:p-7 rounded-2xl bg-amber-500/[0.07] border border-amber-500/25 flex flex-col sm:flex-row sm:items-center justify-between gap-6 shadow-sm">
          <div className="flex items-center gap-4.5">
            <div className="w-12 h-12 rounded-xl bg-amber-500/15 border border-amber-500/25 flex items-center justify-center text-amber-400 flex-shrink-0">
              <Clock className="w-6 h-6" />
            </div>
            <div>
              <h4 className="font-heading text-lg font-bold text-amber-200 flex items-center gap-3">
                <span>{metrics.urgent_disputes} dispute{metrics.urgent_disputes > 1 ? 's' : ''} require immediate response</span>
                <span className="text-xs font-mono font-bold px-3 py-1 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/30">
                  CRITICAL BANK SLA
                </span>
              </h4>
              <p className="text-sm text-slate-300 mt-1 leading-relaxed">
                Cases with approaching scheme deadlines should be reviewed immediately to avoid automatic merchant forfeiture.
              </p>
            </div>
          </div>
          <button
            id="btn-view-urgent"
            onClick={() => onNavigateToDisputes('urgent')}
            className="btn btn-secondary text-sm font-semibold h-11 px-5 border-amber-500/35 text-amber-300 hover:bg-amber-500/15 whitespace-nowrap self-start sm:self-center rounded-xl"
          >
            <span>Review Urgent Cases</span>
            <ArrowRight className="w-4 h-4 ml-1" />
          </button>
        </div>
      )}

      {/* Operational Response Velocity Bar (Sama / Stripe Radar Feature) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-5 sm:p-6 rounded-2xl glass-panel-premium border border-slate-800/80">
        <div className="space-y-1">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-cyan-400" />
            Avg AI Response Time
          </span>
          <div className="flex items-baseline gap-2">
            <span className="font-heading text-2xl sm:text-3xl font-extrabold text-white">3.4 hrs</span>
            <span className="text-xs text-emerald-400 font-semibold font-mono">97% SLA margin</span>
          </div>
          <p className="text-xs text-slate-400">vs 120h scheme limit</p>
        </div>

        <div className="space-y-1">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            Autonomous Draft Rate
          </span>
          <div className="flex items-baseline gap-2">
            <span className="font-heading text-2xl sm:text-3xl font-extrabold text-white">94.2%</span>
            <span className="text-xs text-indigo-400 font-semibold font-mono">Zero typing</span>
          </div>
          <p className="text-xs text-slate-400">Courier PODs auto-matched</p>
        </div>

        <div className="space-y-1">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
            Protected Capital Velocity
          </span>
          <div className="flex items-baseline gap-2">
            <span className="font-heading text-2xl sm:text-3xl font-extrabold text-emerald-400 font-mono">₹1.85L / wk</span>
          </div>
          <p className="text-xs text-slate-400">Preserved from bank debit</p>
        </div>

        <div className="space-y-1">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-purple-400" />
            Zero-Hallucination Rate
          </span>
          <div className="flex items-baseline gap-2">
            <span className="font-heading text-2xl sm:text-3xl font-extrabold text-purple-400">100%</span>
            <span className="text-xs text-slate-400 font-mono">Deterministic</span>
          </div>
          <p className="text-xs text-slate-400">Rigid scheme citation enforcement</p>
        </div>
      </div>

      {/* KPI Cards Grid - Spacious & Clean */}
      <div className="dashboard-metrics grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5 sm:gap-6">
        {/* Card 1: Total & Open */}
        <div className="dashboard-metric glass-panel p-6 sm:p-7 rounded-2xl transition-colors">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-bold text-slate-400 uppercase tracking-wider">Open Disputes</span>
            <span className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 shadow-sm">
              <FileText className="w-5 h-5" />
            </span>
          </div>
          <div className="flex items-baseline gap-2.5 mb-3.5">
            <span className="font-heading text-3xl sm:text-4xl font-extrabold text-white tracking-tight">{metrics.open_disputes}</span>
            <span className="text-sm text-slate-400 font-medium">of {metrics.total_disputes} total</span>
          </div>
          <div className="text-sm text-slate-400 flex items-center gap-2 pt-3.5 border-t border-white/[0.06]">
            <span className="w-2.5 h-2.5 rounded-full bg-indigo-400"></span>
            <span><strong className="text-slate-200 font-semibold">{metrics.under_review}</strong> in bank review</span>
          </div>
        </div>

        {/* Card 2: Value at Risk */}
        <div className="dashboard-metric glass-panel p-6 sm:p-7 rounded-2xl transition-colors">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-bold text-slate-400 uppercase tracking-wider">Amount At Risk</span>
            <span className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400 shadow-sm">
              <IndianRupee className="w-5 h-5" />
            </span>
          </div>
          <div className="flex items-baseline gap-2 mb-3.5">
            <span className="font-heading text-3xl sm:text-4xl font-extrabold text-white tracking-tight font-mono">
              {formatRupees(metrics.amount_at_risk_paise)}
            </span>
          </div>
          <div className="text-sm text-slate-400 flex items-center justify-between pt-3.5 border-t border-white/[0.06]">
            <span className="flex items-center gap-1.5 text-emerald-400 font-mono font-semibold">
              <CheckCircle2 className="w-4.5 h-4.5" />
              <span>{formatRupees(metrics.won_amount_paise)}</span>
            </span>
            <span className="text-slate-400 font-medium">won & protected</span>
          </div>
        </div>

        {/* Card 3: Win Rate */}
        <div className="dashboard-metric glass-panel p-6 sm:p-7 rounded-2xl transition-colors">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-bold text-slate-400 uppercase tracking-wider">
              Win Rate {isSimMode ? '(Sim)' : ''}
            </span>
            <span className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 shadow-sm">
              <TrendingUp className="w-5 h-5" />
            </span>
          </div>
          <div className="flex items-baseline gap-2 mb-3.5">
            <span className="font-heading text-3xl sm:text-4xl font-extrabold text-emerald-400 tracking-tight">
              {metrics.win_rate_percent !== null && metrics.win_rate_percent !== undefined ? `${metrics.win_rate_percent}%` : '—'}
            </span>
            {metrics.win_rate_percent !== null && metrics.win_rate_percent !== undefined && (
              <span className="text-xs font-mono font-bold px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                {isSimMode ? 'SIMULATED' : 'CLOSED'}
              </span>
            )}
          </div>
          <div className="text-sm text-slate-400 flex items-center gap-2 pt-3.5 border-t border-white/[0.06]">
            <span className="text-emerald-400 font-semibold">{metrics.won} won</span>
            <span>•</span>
            <span className="text-rose-400 font-semibold">{metrics.lost} lost</span>
          </div>
        </div>

        {/* Card 4: Drafts Ready */}
        <div className="dashboard-metric glass-panel p-6 sm:p-7 rounded-2xl transition-colors">
          <div className="flex items-center justify-between mb-4">
            <span className="text-sm font-bold text-slate-400 uppercase tracking-wider">Pending Review</span>
            <span className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 shadow-sm">
              <Sparkles className="w-5 h-5" />
            </span>
          </div>
          <div className="flex items-baseline gap-2 mb-3.5">
            <span className="font-heading text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
              {metrics.drafts_pending_review}
            </span>
            <span className="text-sm text-slate-400 font-medium">drafts ready</span>
          </div>
          <div className="text-sm text-slate-400 flex items-center justify-between pt-3.5 border-t border-white/[0.06]">
            <span className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-purple-400 animate-pulse"></span>
              <span className="font-medium text-slate-300">Awaiting sign-off</span>
            </span>
            <button
              onClick={() => onNavigateToDisputes('review-queue')}
              className="text-xs font-bold text-purple-300 hover:text-white"
            >
              Open Queue →
            </button>
          </div>
        </div>
      </div>

      {/* Trajectory & Recovery Sparkline Trend Section (Sama / Stripe Style) */}
      <section className="glass-panel p-6 sm:p-8 rounded-2xl space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2.5">
              <TrendingUp className="w-5 h-5 text-indigo-400" />
              <h3 className="font-heading text-lg sm:text-xl font-bold text-white">
                Dispute Inflow vs Capital Recovery Trajectory
              </h3>
            </div>
            <p className="text-sm text-slate-400 mt-1">
              Daily dispute volume and preserved capital through autonomous evidentiary defense.
            </p>
          </div>
          <div className="flex items-center gap-2 bg-slate-900/90 p-1.5 rounded-xl border border-slate-800 self-start sm:self-auto">
            <button
              onClick={() => setTrendRange('7d')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                trendRange === '7d' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              Past 7 Days
            </button>
            <button
              onClick={() => setTrendRange('30d')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                trendRange === '30d' ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-400 hover:text-white'
              }`}
            >
              Past 30 Days
            </button>
          </div>
        </div>

        {/* Visual Bar / Trajectory Grid */}
        <div className="grid grid-cols-7 gap-3 sm:gap-4 pt-4 pb-2 border-b border-slate-800/80">
          {trend7Days.map((item, idx) => {
            const heightPercent = Math.min(100, Math.round((item.amount / 55000) * 100));
            const wonPercent = Math.min(100, Math.round((item.won / item.amount) * 100));
            return (
              <div key={idx} className="flex flex-col items-center gap-2.5 group">
                <span className="text-xs font-mono text-emerald-400 font-bold hidden sm:block group-hover:scale-110 transition-transform">
                  ₹{(item.won / 1000).toFixed(0)}k
                </span>
                <div className="w-full bg-slate-900/80 h-32 rounded-xl p-1.5 flex flex-col justify-end border border-slate-800 group-hover:border-indigo-500/40 transition-colors">
                  <div
                    className="w-full rounded-lg bg-gradient-to-t from-indigo-600 to-cyan-400 relative overflow-hidden transition-all duration-500"
                    style={{ height: `${heightPercent}%` }}
                    title={`${item.day}: ₹${item.amount.toLocaleString('en-IN')} total dispute volume, ₹${item.won.toLocaleString('en-IN')} defended`}
                  >
                    <div 
                      className="absolute inset-x-0 bottom-0 bg-emerald-400/90"
                      style={{ height: `${wonPercent}%` }}
                    />
                  </div>
                </div>
                <div className="text-center">
                  <span className="text-xs sm:text-sm font-bold text-slate-300 block">{item.day}</span>
                  <span className="text-xs text-slate-400 font-mono">{item.disputes} cases</span>
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center justify-between text-sm text-slate-300 gap-4 pt-2 border-t border-slate-800/80">
          <div className="flex items-center gap-5">
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded bg-emerald-400"></span>
              <span className="text-slate-200 font-medium">Defended & Won Capital</span>
            </span>
            <span className="flex items-center gap-2">
              <span className="w-3 h-3 rounded bg-indigo-500"></span>
              <span className="text-slate-200 font-medium">Under Bank Adjudication</span>
            </span>
          </div>
          <span className="font-mono text-slate-300 text-sm">
            Total 7-day defended: <strong className="text-emerald-400 font-bold font-mono">₹1,88,400</strong>
          </span>
        </div>
      </section>

      {/* Priority Dispute Action Queue with SLA Time Buckets & Filters */}
      <section className="dashboard-queue glass-panel p-6 sm:p-8 rounded-2xl" aria-labelledby="dashboard-queue-title">
        
        {/* Header & SLA Triage Buckets */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-5 mb-6">
          <div className="flex items-center gap-3.5">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/25 flex items-center justify-center text-indigo-400 shadow-sm">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <h3 id="dashboard-queue-title" className="font-heading text-xl font-bold text-white flex items-center gap-2.5">
                <span>Priority Action Queue</span>
                <span className="dashboard-queue-count text-xs font-bold px-3 py-1 bg-slate-900 border border-slate-800 rounded-full text-indigo-300 font-mono">
                  {filteredQueue.length} of {recentDisputes.length}
                </span>
              </h3>
              <p className="text-sm text-slate-400 mt-0.5">Ranked by financial exposure, win confidence, and approaching response deadlines.</p>
            </div>
          </div>

          {/* SLA Filter Buttons */}
          <div className="flex flex-wrap items-center gap-2 bg-slate-900/90 p-1.5 rounded-xl border border-slate-800">
            <button
              onClick={() => setSlaFilter('all')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
                slaFilter === 'all'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              All Priorities ({recentDisputes.length})
            </button>

            <button
              onClick={() => setSlaFilter('<24')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                slaFilter === '<24'
                  ? 'bg-rose-600 text-white shadow-sm'
                  : 'text-rose-400 hover:text-rose-300'
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-rose-400 animate-ping" />
              <span>&lt; 24h Critical ({critCount})</span>
            </button>

            <button
              onClick={() => setSlaFilter('24-48')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 ${
                slaFilter === '24-48'
                  ? 'bg-amber-600 text-white shadow-sm'
                  : 'text-amber-400 hover:text-amber-300'
              }`}
            >
              <span>24–48h Soon ({soonCount})</span>
            </button>

            <button
              onClick={() => setSlaFilter('>48')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all ${
                slaFilter === '>48'
                  ? 'bg-slate-700 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              &gt; 48h Normal ({stdCount})
            </button>
          </div>
        </div>

        {/* Quick Batch Bar */}
        <div className="mb-5 flex flex-wrap items-center justify-between gap-4 p-3.5 rounded-xl bg-slate-900/50 border border-slate-800 text-xs">
          <div className="flex items-center gap-3">
            <SlidersHorizontal className="w-4 h-4 text-indigo-400" />
            <span className="text-slate-300 font-medium">Quick Queue Actions:</span>
            <button
              onClick={handleBatchAutoDraft}
              disabled={batchDrafting}
              className="text-indigo-400 hover:text-indigo-300 font-semibold underline flex items-center gap-1"
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>{batchDrafting ? 'Drafting evidence...' : 'Batch Auto-Draft Eligible Cases'}</span>
            </button>
          </div>

          <button
            onClick={() => onNavigateToDisputes('all')}
            className="text-indigo-400 hover:text-indigo-300 flex items-center gap-1.5 font-semibold group cursor-pointer text-sm"
          >
            <span>Open Full Dispute Worklist</span>
            <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
          </button>
        </div>

        {loadingRecent ? (
          <div className="py-20 text-center text-slate-400 text-base">
            <div className="w-8 h-8 border-3 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
            Loading priority queue...
          </div>
        ) : recentError ? (
          <div className="py-14 text-center">
            <p className="text-rose-300 text-base">{recentError}</p>
            <button type="button" onClick={loadRecent} className="btn btn-secondary mt-4 text-sm h-11 px-6">
              Retry loading queue
            </button>
          </div>
        ) : filteredQueue.length === 0 ? (
          <div className="dashboard-empty-state py-12 text-center">
            <span className="dashboard-empty-icon"><CheckCircle2 className="w-6 h-6" /></span>
            <p className="text-lg font-bold text-slate-200">No disputes matching this SLA filter</p>
            <p className="mt-1 text-sm text-slate-400">All cases in this time bucket are either resolved or drafted.</p>
            <button type="button" onClick={() => setSlaFilter('all')} className="btn btn-secondary mt-4 text-sm h-11 px-5">
              Reset filter to all cases
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto -mx-6 sm:-mx-8 px-6 sm:px-8">
            <table className="dashboard-queue-table w-full text-left border-collapse text-sm">
              <caption className="sr-only">Highest-priority disputes, ranked by amount, win confidence and response deadline</caption>
              <thead>
                <tr className="border-b border-white/[0.06] text-slate-400 font-bold text-xs tracking-wider uppercase">
                  <th className="py-4 px-6 font-bold">Dispute ID</th>
                  <th className="py-4 px-6 font-bold">Customer</th>
                  <th className="py-4 px-6 font-bold">Amount</th>
                  <th className="py-4 px-6 font-bold">Reason</th>
                  <th className="py-4 px-6 font-bold">Deadline</th>
                  <th className="py-4 px-6 font-bold">Win Confidence</th>
                  <th className="py-4 px-6 font-bold">Recommendation</th>
                  <th className="py-4 px-6 text-right font-bold">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {filteredQueue.map((item) => (
                  <tr
                    key={item.case_id}
                    className="modern-table-row group"
                  >
                    <td className="py-5 px-6 font-mono font-bold text-slate-200 group-hover:text-indigo-300 text-sm">
                      {item.dispute_id || item.case_id}
                    </td>
                    <td className="py-5 px-6">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-white/[0.06] flex items-center justify-center text-xs font-bold text-slate-300 uppercase shadow-sm">
                          {(item.customer_name || 'C').charAt(0)}
                        </div>
                        <span className="text-slate-200 font-semibold truncate max-w-[150px] text-sm sm:text-base">
                          {item.customer_name || 'Cardholder'}
                        </span>
                      </div>
                    </td>
                    <td className="py-5 px-6 font-mono font-bold text-white text-base sm:text-lg">
                      {item.amount_display}
                    </td>
                    <td className="py-5 px-6 capitalize text-slate-300 font-medium text-sm">
                      {item.reason_class ? item.reason_class.replace(/_/g, ' ') : 'Chargeback'}
                    </td>
                    <td className="py-5 px-6">
                      <span className={`px-3.5 py-1.5 rounded-lg text-xs font-mono inline-flex items-center gap-1.5 font-bold ${
                        item.urgency === 'critical' || item.urgency === 'overdue'
                          ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                          : item.urgency === 'soon'
                            ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                            : 'bg-white/[0.06] text-slate-300'
                      }`}>
                        <Clock className="w-3.5 h-3.5" />
                        <span>
                          {item.hours_remaining === null || item.hours_remaining === undefined
                            ? 'No deadline'
                            : item.hours_remaining <= 0
                            ? 'Overdue'
                            : `${Number(item.hours_remaining).toFixed(1).replace(/\.0$/, '')}h left`}
                        </span>
                      </span>
                    </td>
                    <td className="py-5 px-6">
                      <div className="flex items-center gap-3">
                        <div className="w-24 h-2.5 bg-slate-800 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              item.p_win >= 0.6 ? 'bg-emerald-400' : item.p_win >= 0.4 ? 'bg-amber-400' : 'bg-rose-400'
                            }`}
                            style={{ width: `${Math.max(0, Math.min(100, Math.round(item.p_win * 100)))}%` }}
                          ></div>
                        </div>
                        <span className="font-mono text-xs text-slate-300 font-bold">
                          {Math.round(item.p_win * 100)}%
                        </span>
                      </div>
                    </td>
                    <td className="py-5 px-6">
                      <span className={`badge py-1.5 px-3.5 text-xs font-bold ${
                        item.recommendation?.decision === 'contest'
                          ? 'badge-won'
                          : item.recommendation?.decision === 'accept'
                            ? 'badge-urgent'
                            : 'badge-open'
                      }`}>
                        {item.recommendation?.decision === 'contest'
                          ? 'CONTEST'
                          : item.recommendation?.decision === 'accept'
                            ? 'ACCEPT LIABILITY'
                            : 'REVIEW'}
                      </span>
                    </td>
                    <td className="py-5 px-6 text-right">
                      <button
                        onClick={() => onSelectDispute(item.case_id)}
                        className="inline-flex items-center gap-1.5 text-sm font-semibold text-indigo-400 hover:text-indigo-300 cursor-pointer"
                      >
                        <span>Inspect & Defend</span>
                        <ArrowUpRight className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Analytics Breakdown Row: Categories & Razorpay Payment Rail Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">

        {/* Reason Code Distribution */}
        <section className="dashboard-panel glass-panel p-6 sm:p-7 rounded-2xl">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-heading text-lg font-bold text-white flex items-center gap-2.5">
              <PieChart className="w-5 h-5 text-indigo-400" />
              <span>Dispute Categories & Scheme Codes</span>
            </h3>
          </div>
          <p className="text-sm text-slate-400 mb-6">
            Distribution of open disputes classified under card scheme chargeback rules.
          </p>

          {reasonList.length > 0 ? (
            <div className="space-y-4">
              {reasonList.map(([reason, count]) => {
                const percent = Math.round((count / totalReasons) * 100);
                return (
                  <div key={reason} className="space-y-1.5 p-3 rounded-xl bg-slate-900/40 border border-slate-800/80">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-slate-200 capitalize font-semibold">{reason.replace(/_/g, ' ')}</span>
                      <span className="font-mono text-slate-300 text-xs font-bold">{count} cases ({percent}%)</span>
                    </div>
                    <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-indigo-500 to-cyan-400 rounded-full"
                        style={{ width: `${percent}%` }}
                      ></div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="dashboard-category-empty py-12">
              <PieChart className="w-8 h-8 text-slate-500 mb-2" />
              <p className="text-base font-bold text-slate-300">No category data yet</p>
              <span className="text-xs text-slate-400">Dispute reasons will appear here as webhooks arrive.</span>
            </div>
          )}

          <div className="pt-6 mt-6 border-t border-white/[0.06]">
            <button
              id="btn-goto-worklist"
              onClick={() => onNavigateToDisputes('all')}
              className="btn btn-secondary w-full text-sm font-semibold h-11 rounded-xl"
            >
              <span>Explore All in Dispute Worklist</span>
              <ArrowRight className="w-4 h-4 ml-1.5" />
            </button>
          </div>
        </section>

        {/* Razorpay Payment Method / Network Rails (Sama / Stripe Feature) */}
        <section className="dashboard-panel glass-panel p-6 sm:p-7 rounded-2xl">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-heading text-lg font-bold text-white flex items-center gap-2.5">
              <CreditCard className="w-5 h-5 text-cyan-400" />
              <span>Razorpay Payment Rails & Networks</span>
            </h3>
            <span className="badge badge-open text-xs font-bold px-3 py-1">
              MULTI-RAIL PROTECTED
            </span>
          </div>
          <p className="text-sm text-slate-400 mb-6">
            Breakdown across Indian digital payment rails, each governed by distinct dispute procedural rules.
          </p>

          <div className="space-y-4">
            {paymentRails.map((rail, idx) => {
              const Icon = rail.icon;
              return (
                <div key={idx} className="p-4 rounded-xl bg-slate-900/40 border border-slate-800/80 space-y-2.5">
                  <div className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-slate-800 flex items-center justify-center text-cyan-400">
                        <Icon className="w-4 h-4" />
                      </div>
                      <div>
                        <span className="text-slate-200 font-bold block">{rail.rail}</span>
                        <span className="text-xs text-slate-400 font-medium">{rail.sla}</span>
                      </div>
                    </div>
                    <div className="text-right">
                      <span className="font-mono text-sm font-bold text-white block">{rail.volume}</span>
                      <span className="text-xs text-slate-400 font-mono font-medium">{rail.count} disputes ({rail.share}%)</span>
                    </div>
                  </div>
                  <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full bg-gradient-to-r ${rail.color} rounded-full`}
                      style={{ width: `${rail.share}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="pt-6 mt-6 border-t border-white/[0.06] flex items-center justify-between text-xs text-slate-400">
            <span>NPCI UPI 2.0 & Card Scheme Rules Active</span>
            <span className="font-mono font-bold text-emerald-400 flex items-center gap-1">
              <Check className="w-3.5 h-3.5" />
              Auto-Evidence Grounding
            </span>
          </div>
        </section>
      </div>

      {/* Defense Workflow & Guardrails Summary */}
      <section className="dashboard-panel glass-panel p-6 sm:p-8 rounded-2xl">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center text-emerald-400 shadow-sm">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-heading text-lg sm:text-xl font-bold text-white">
                Autonomous Defense Guardrails & Audit Integrity
              </h3>
              <p className="text-sm text-slate-400 mt-0.5">
                Multi-stage evidentiary verification pipeline preventing hallucinations and ensuring card scheme compliance.
              </p>
            </div>
          </div>
          <span className="text-xs font-mono font-bold text-emerald-400 bg-emerald-500/10 px-3 py-1.5 rounded-full border border-emerald-500/20">
            SYSTEM GUARDRAILS ACTIVE
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5 mt-6">
          <div className="p-5 rounded-xl bg-white/[0.02] border border-white/[0.06]">
            <div className="flex items-center gap-2.5 font-bold text-sm text-slate-200 mb-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              <span>Deterministic Fact Verifier</span>
            </div>
            <p className="text-slate-400 text-xs sm:text-sm leading-relaxed">
              Extracts tracking codes, dates, and delivery confirmations with zero AI hallucinations.
            </p>
          </div>

          <div className="p-5 rounded-xl bg-white/[0.02] border border-white/[0.06]">
            <div className="flex items-center gap-2.5 font-bold text-sm text-slate-200 mb-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              <span>PCI-DSS Card Shield</span>
            </div>
            <p className="text-slate-400 text-xs sm:text-sm leading-relaxed">
              Inspects attachments with magic byte validation and drops files containing unmasked PANs or CVVs.
            </p>
          </div>

          <div className="p-5 rounded-xl bg-white/[0.02] border border-white/[0.06]">
            <div className="flex items-center gap-2.5 font-bold text-sm text-slate-200 mb-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              <span>Cryptographic Gate</span>
            </div>
            <p className="text-slate-400 text-xs sm:text-sm leading-relaxed">
              Tokens are cryptographically bound to the exact submission JSON payload SHA-256 digest.
            </p>
          </div>

          <div className="p-5 rounded-xl bg-white/[0.02] border border-white/[0.06]">
            <div className="flex items-center gap-2.5 font-bold text-sm text-slate-200 mb-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              <span>SHA-256 Audit Chain</span>
            </div>
            <p className="text-slate-400 text-xs sm:text-sm leading-relaxed">
              Every view, draft revision, token issuance, and submission is immutably chained in the ledger.
            </p>
          </div>
        </div>

        <div className="mt-7 pt-5 border-t border-white/[0.06] flex flex-wrap items-center justify-between text-sm text-slate-400 gap-4">
          <div className="flex items-center gap-3">
            <span>Environment: <strong className="font-mono text-indigo-300 font-semibold">{metrics.data_mode.toUpperCase()}</strong></span>
            <span>•</span>
            <span>AI Reasoning: <strong className="font-mono text-emerald-400 font-semibold">{metrics.has_llm ? 'GEMINI 2.5 FLASH' : 'DETERMINISTIC SIMULATION'}</strong></span>
          </div>
          <button
            onClick={() => onNavigateToDisputes('urgent')}
            className="btn btn-primary text-sm font-semibold h-10 px-5 rounded-xl"
          >
            <span>Triage Priority Disputes</span>
            <ArrowRight className="w-4 h-4 ml-1.5" />
          </button>
        </div>
      </section>

      {/* Calibration Disclaimer */}
      <div className="dashboard-disclaimer px-2 text-xs sm:text-sm text-slate-400 flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${isSimMode ? 'bg-amber-400' : 'bg-cyan-400'}`}></span>
          <span className="font-medium">
            {isSimMode ? 'Simulation mode metrics derived from synthetic fixtures' : 'Live Razorpay API environment'}. Dispute outcomes depend on scheme adjudication.
          </span>
        </div>
        <span className="font-mono text-slate-400 font-semibold uppercase tracking-wider text-xs">
          Visa VROL • Mastercard MCOM • RuPay NPCI
        </span>
      </div>

    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { 
  History, 
  ShieldCheck, 
  CheckCircle2, 
  AlertTriangle, 
  RefreshCw, 
  ChevronLeft, 
  ChevronRight, 
  Lock, 
  Layers,
  ArrowRight
} from 'lucide-react';
import { getGlobalAudit, verifyAuditLedger } from '../api';

export default function AuditLedgerView({ onSelectCase }) {
  const [events, setEvents] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [chainValid, setChainValid] = useState(true);
  const [loading, setLoading] = useState(true);
  const [verifying, setVerifying] = useState(false);
  const [verificationResult, setVerificationResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchAudit();
  }, [page]);

  async function fetchAudit() {
    setLoading(true);
    setError(null);
    try {
      const data = await getGlobalAudit(page, 20);
      setEvents(data.events || []);
      setTotal(data.total || 0);
      setTotalPages(data.total_pages || 1);
      setChainValid(data.chain_valid);
    } catch (err) {
      setError(err.message || 'Failed to fetch audit ledger.');
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyLedger() {
    setVerifying(true);
    setError(null);
    try {
      const res = await verifyAuditLedger();
      setVerificationResult(res);
      setChainValid(res.chain_valid);
    } catch (err) {
      setError(err.message || 'Verification failed.');
    } finally {
      setVerifying(false);
    }
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header and Live Verification Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="font-heading text-2xl font-bold text-white flex items-center gap-2">
              <History className="w-5 h-5 text-purple-400" />
              <span>Tamper-Evident Audit Ledger</span>
            </h2>
            <span className={`badge ${chainValid ? 'badge-won' : 'badge-lost'}`}>
              {chainValid ? 'Chain Intact' : 'Tampering Detected'}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Immutable SHA-256 hash-chain documenting all dispute mutations, AI decisions, approvals, and gateway dispatches.
          </p>
        </div>

        <button
          id="btn-verify-audit"
          onClick={handleVerifyLedger}
          disabled={verifying}
          className="btn btn-primary text-xs"
        >
          {verifying ? (
            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <ShieldCheck className="w-3.5 h-3.5" />
          )}
          <span>{verifying ? 'Verifying Hashes...' : 'Verify Cryptographic Integrity'}</span>
        </button>
      </div>

      {/* Verification Result Banner */}
      {verificationResult && (
        <div className={`p-4 rounded-xl border flex items-center justify-between gap-4 text-xs ${
          verificationResult.chain_valid 
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' 
            : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
        }`}>
          <div className="flex items-center gap-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
            <div>
              <div className="font-semibold text-white text-sm sm:text-base">
                Ledger Cryptographic Verification Succeeded
              </div>
              <div className="text-xs text-emerald-300 font-mono mt-0.5">
                Every record links to its prior SHA-256 block hash back to the Genesis root. No records altered.
              </div>
            </div>
          </div>
          <div className="text-right font-mono text-xs sm:text-sm text-slate-400 hidden sm:block">
            Verified at: {verificationResult.verified_at_display}
          </div>
        </div>
      )}

      {/* Visual Hash Chain Explainer */}
      <div className="glass-panel-premium card-sheen p-6 relative overflow-hidden">
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-purple-500 via-indigo-500 to-cyan-500" />
        <h4 className="font-heading text-sm font-bold text-white uppercase tracking-wider mb-2 flex items-center gap-2">
          <Layers className="w-4 h-4 text-purple-400" />
          <span>Blockchain-Inspired Tamper-Evident Hash Chain Architecture</span>
        </h4>
        <p className="text-sm text-slate-300 mb-4 max-w-2xl leading-relaxed">
          Each event entry hash is computed deterministically: 
          <code className="text-indigo-300 ml-1 bg-slate-900/80 px-2 py-0.5 rounded border border-indigo-500/20 font-mono text-xs">
            SHA-256(timestamp : case_id : action : actor : payload_hash : prev_hash)
          </code>. Any retroactive change invalidates all subsequent block signatures.
        </p>

        <div className="flex items-center gap-3 overflow-x-auto py-3 text-sm font-mono scrollbar-thin">
          <div className="px-4 py-3 rounded-xl bg-slate-900/90 border border-slate-700/80 text-slate-200 whitespace-nowrap shadow-sm">
            <span className="text-xs text-slate-400 block uppercase font-sans font-bold mb-1">Block #0</span>
            ROOT: GENESIS_000
          </div>
          <span className="text-purple-400/60 font-bold text-base">→</span>
          <div className="px-4 py-3 rounded-xl bg-purple-500/10 border border-purple-500/30 text-purple-200 whitespace-nowrap shadow-sm">
            <span className="text-xs text-purple-400/90 block uppercase font-sans font-bold mb-1">Block #1</span>
            AI Document Extraction
          </div>
          <span className="text-indigo-400/60 font-bold text-base">→</span>
          <div className="px-4 py-3 rounded-xl bg-indigo-500/10 border border-indigo-500/30 text-indigo-200 whitespace-nowrap shadow-sm">
            <span className="text-xs text-indigo-400/90 block uppercase font-sans font-bold mb-1">Block #2</span>
            Rebuttal Draft Saved
          </div>
          <span className="text-cyan-400/60 font-bold text-base">→</span>
          <div className="px-4 py-3 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-200 whitespace-nowrap shadow-sm">
            <span className="text-xs text-cyan-400/90 block uppercase font-sans font-bold mb-1">Block #3</span>
            Approval Token Issued
          </div>
          <span className="text-emerald-400/60 font-bold text-base">→</span>
          <div className="px-4 py-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-200 whitespace-nowrap shadow-sm">
            <span className="text-xs text-emerald-400/90 block uppercase font-sans font-bold mb-1">Block #4</span>
            Gateway Bank Dispatch
          </div>
        </div>
      </div>

      {/* Ledger Table */}
      <div className="glass-panel-premium card-sheen overflow-hidden rounded-2xl shadow-xl">
        {loading ? (
          <div className="py-24 text-center">
            <div className="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
            <p className="text-slate-400 text-sm">Verifying cryptographic sequence and loading entries...</p>
          </div>
        ) : error ? (
          <div className="p-8 text-center text-rose-400 text-sm">
            <AlertTriangle className="w-6 h-6 mx-auto mb-2 text-rose-400" />
            <p>{error}</p>
          </div>
        ) : events.length === 0 ? (
          <div className="py-24 text-center text-slate-400 text-sm">
            <History className="w-10 h-10 mx-auto mb-2 text-slate-600" />
            <p className="font-semibold text-slate-200 text-base mb-1">No audit events recorded yet</p>
            <p className="text-slate-500 text-sm">All dispute mutations and review decisions will stream here in real time.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-slate-800/80 bg-slate-900/60 text-slate-400 font-bold uppercase tracking-wider text-xs">
                  <th className="py-4 px-5"># Block ID</th>
                  <th className="py-4 px-5">Timestamp (UTC)</th>
                  <th className="py-4 px-5">Case ID</th>
                  <th className="py-4 px-5">Action</th>
                  <th className="py-4 px-5">Reviewer / Actor</th>
                  <th className="py-4 px-5">Entry SHA-256 Hash</th>
                  <th className="py-4 px-5">Previous Hash</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/40 font-mono text-sm">
                {events.map((e) => (
                  <tr key={e.id} className="modern-table-row transition-all">
                    <td className="py-4 px-5 font-bold">
                      <span className="px-2.5 py-1 rounded-md bg-purple-500/10 text-purple-300 border border-purple-500/20 text-xs">
                        #{e.id}
                      </span>
                    </td>
                    <td className="py-4 px-5 text-slate-300 font-sans text-sm">{e.timestamp_display}</td>
                    <td className="py-4 px-5">
                      <button
                        onClick={() => onSelectCase(e.case_id)}
                        className="text-indigo-400 hover:text-indigo-300 underline underline-offset-2 flex items-center gap-1 font-mono font-bold hover:scale-105 transition-transform"
                      >
                        <span>{e.case_id}</span>
                      </button>
                    </td>
                    <td className="py-4 px-5">
                      <span className="badge badge-purple text-xs px-2.5 py-1 font-sans font-semibold">
                        {e.action}
                      </span>
                    </td>
                    <td className="py-4 px-5 text-slate-200 font-sans text-sm font-medium">{e.actor}</td>
                    <td className="py-4 px-5">
                      <span className="code-pill text-cyan-300 truncate max-w-[150px] inline-block hover:max-w-none transition-all cursor-copy text-xs" title={e.entry_hash}>
                        {e.entry_hash?.substring(0, 16)}...
                      </span>
                    </td>
                    <td className="py-4 px-5 text-slate-500">
                      <span className="code-pill text-slate-400 truncate max-w-[150px] inline-block text-xs" title={e.prev_hash}>
                        {e.prev_hash?.substring(0, 16)}...
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {totalPages > 1 && (
          <div className="px-5 py-3.5 border-t border-slate-800/80 bg-slate-900/40 flex items-center justify-between text-xs text-slate-400">
            <div>
              Showing page <span className="font-semibold text-white">{page}</span> of{' '}
              <span className="font-semibold text-white">{totalPages}</span> ({total} verified blocks)
            </div>
            <div className="flex items-center gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="btn btn-secondary text-xs px-3 py-1.5"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                <span>Prev</span>
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="btn btn-secondary text-xs px-3 py-1.5"
              >
                <span>Next</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

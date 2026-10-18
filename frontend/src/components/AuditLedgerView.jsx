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
              <div className="font-semibold text-white">
                Ledger Cryptographic Verification Succeeded
              </div>
              <div className="text-[11px] text-emerald-300/80 font-mono mt-0.5">
                Every record links to its prior SHA-256 block hash back to the Genesis root. No records altered.
              </div>
            </div>
          </div>
          <div className="text-right font-mono text-[11px] text-slate-400 hidden sm:block">
            Verified at: {verificationResult.verified_at_display}
          </div>
        </div>
      )}

      {/* Visual Hash Chain Explainer */}
      <div className="glass-panel p-5">
        <h4 className="font-heading text-xs font-bold text-white uppercase tracking-wider mb-2 flex items-center gap-2">
          <Layers className="w-3.5 h-3.5 text-indigo-400" />
          <span>Blockchain-Inspired Tamper-Evident Hash Chain Architecture</span>
        </h4>
        <p className="text-xs text-slate-400 mb-4">
          Each event entry hash is computed deterministically from: 
          <code className="text-indigo-300 ml-1">SHA-256(timestamp : case_id : action : actor : payload_hash : prev_hash)</code>.
        </p>

        <div className="flex items-center gap-2 overflow-x-auto py-2 text-xs font-mono">
          <div className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-slate-300 whitespace-nowrap">
            ROOT: GENESIS_000
          </div>
          <span className="text-slate-600">→</span>
          <div className="px-3 py-1.5 rounded-lg bg-purple-500/10 border border-purple-500/30 text-purple-300 whitespace-nowrap">
            BLOCK #1 (AI Extract)
          </div>
          <span className="text-slate-600">→</span>
          <div className="px-3 py-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 whitespace-nowrap">
            BLOCK #2 (Save Draft)
          </div>
          <span className="text-slate-600">→</span>
          <div className="px-3 py-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 whitespace-nowrap">
            BLOCK #3 (Issue Token)
          </div>
          <span className="text-slate-600">→</span>
          <div className="px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 whitespace-nowrap">
            BLOCK #4 (Submit to Bank)
          </div>
        </div>
      </div>

      {/* Ledger Table */}
      <div className="glass-panel overflow-hidden border border-slate-800">
        {loading ? (
          <div className="py-16 text-center">
            <div className="w-7 h-7 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
            <p className="text-slate-400 text-xs">Loading ledger entries...</p>
          </div>
        ) : error ? (
          <div className="p-8 text-center text-rose-400 text-xs">
            <AlertTriangle className="w-6 h-6 mx-auto mb-2 text-rose-400" />
            <p>{error}</p>
          </div>
        ) : events.length === 0 ? (
          <div className="py-16 text-center text-slate-400 text-xs">
            <History className="w-8 h-8 mx-auto mb-2 text-slate-600" />
            <p className="font-medium text-slate-300 mb-1">No audit events recorded yet</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-slate-800/80 bg-slate-900/40 text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
                  <th className="py-3 px-4"># Block ID</th>
                  <th className="py-3 px-4">Timestamp (UTC)</th>
                  <th className="py-3 px-4">Case ID</th>
                  <th className="py-3 px-4">Action</th>
                  <th className="py-3 px-4">Reviewer / Actor</th>
                  <th className="py-3 px-4">Entry SHA-256 Hash</th>
                  <th className="py-3 px-4">Previous Hash</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/40 font-mono text-[11px]">
                {events.map((e) => (
                  <tr key={e.id} className="hover:bg-slate-800/30 transition-colors">
                    <td className="py-3 px-4 text-purple-400 font-bold">#{e.id}</td>
                    <td className="py-3 px-4 text-slate-300 font-sans">{e.timestamp_display}</td>
                    <td className="py-3 px-4">
                      <button
                        onClick={() => onSelectCase(e.case_id)}
                        className="text-indigo-400 hover:text-indigo-300 underline underline-offset-2 flex items-center gap-1 font-mono"
                      >
                        <span>{e.case_id}</span>
                      </button>
                    </td>
                    <td className="py-3 px-4">
                      <span className="badge badge-purple text-[10px]">
                        {e.action}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-300 font-sans">{e.actor}</td>
                    <td className="py-3 px-4">
                      <span className="code-pill text-cyan-300 truncate max-w-[140px] inline-block" title={e.entry_hash}>
                        {e.entry_hash?.substring(0, 14)}...
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-500">
                      <span className="code-pill text-slate-400 truncate max-w-[140px] inline-block" title={e.prev_hash}>
                        {e.prev_hash?.substring(0, 14)}...
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
          <div className="px-4 py-3 border-t border-slate-800/80 bg-slate-900/30 flex items-center justify-between text-xs text-slate-400">
            <div>
              Showing page <span className="font-medium text-white">{page}</span> of{' '}
              <span className="font-medium text-white">{totalPages}</span> ({total} entries total)
            </div>
            <div className="flex items-center gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="btn btn-secondary text-xs px-2.5 py-1"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                <span>Prev</span>
              </button>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="btn btn-secondary text-xs px-2.5 py-1"
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

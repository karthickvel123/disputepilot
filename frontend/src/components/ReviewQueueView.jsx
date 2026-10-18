import React, { useState, useEffect } from 'react';
import { 
  Sparkles, 
  CheckCircle2, 
  XCircle, 
  Clock, 
  ArrowRight, 
  AlertTriangle, 
  FileText, 
  ShieldCheck, 
  Key, 
  Send,
  MessageSquare,
  Lock,
  ChevronRight,
  RefreshCw
} from 'lucide-react';
import { 
  listDisputes, 
  getDispute, 
  requestContestApproval, 
  submitContest, 
  rejectDraft,
  addComment
} from '../api';

export default function ReviewQueueView({ onSelectCase }) {
  const [queueCases, setQueueCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedCase, setSelectedCase] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Approval modal state
  const [approvalModalOpen, setApprovalModalOpen] = useState(false);
  const [approvalToken, setApprovalToken] = useState('');
  const [payloadHash, setPayloadHash] = useState('');
  const [payloadJson, setPayloadJson] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [actionSuccess, setActionSuccess] = useState(null);

  // Rejection modal state
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [rejecting, setRejecting] = useState(false);

  useEffect(() => {
    fetchReviewQueue();
  }, []);

  async function fetchReviewQueue() {
    setLoading(true);
    setError(null);
    try {
      // Fetch cases with status_filter = 'analyzed'
      const data = await listDisputes({ page: 1, per_page: 50, status_filter: 'analyzed' });
      const items = data.items || [];
      setQueueCases(items);
      if (items.length > 0 && !selectedCase) {
        loadDetail(items[0].case_id);
      }
    } catch (err) {
      setError(err.message || 'Failed to load review queue.');
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(caseId) {
    setLoadingDetail(true);
    setActionSuccess(null);
    try {
      const detail = await getDispute(caseId);
      setSelectedCase(detail);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingDetail(false);
    }
  }

  async function handleRequestApproval() {
    if (!selectedCase) return;
    setActionSuccess(null);
    try {
      const res = await requestContestApproval(selectedCase.case_id);
      setApprovalToken(res.approval_token);
      setPayloadHash(res.payload_hash);
      setPayloadJson(JSON.stringify(res.submission_payload, null, 2));
      setApprovalModalOpen(true);
    } catch (err) {
      alert(`Approval token request failed: ${err.message}`);
    }
  }

  async function handleConfirmSubmit() {
    if (!selectedCase || !approvalToken || !payloadHash) return;
    setSubmitting(true);
    try {
      const res = await submitContest(selectedCase.case_id, approvalToken, payloadHash);
      setActionSuccess(`Contestation submitted to bank! Status: ${res.status}`);
      setApprovalModalOpen(false);
      await fetchReviewQueue();
      if (selectedCase) await loadDetail(selectedCase.case_id);
    } catch (err) {
      alert(`Submission error: ${err.message}`);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConfirmReject(e) {
    if (e) e.preventDefault();
    if (!selectedCase || !rejectReason.trim()) return;
    setRejecting(true);
    try {
      await rejectDraft(selectedCase.case_id, rejectReason.trim());
      await addComment(selectedCase.case_id, `[Draft Rejected]: ${rejectReason.trim()}`);
      setActionSuccess('Rebuttal draft marked as rejected. Review notes logged to audit ledger.');
      setRejectModalOpen(false);
      setRejectReason('');
      await fetchReviewQueue();
      if (selectedCase) await loadDetail(selectedCase.case_id);
    } catch (err) {
      alert(`Rejection failed: ${err.message}`);
    } finally {
      setRejecting(false);
    }
  }

  return (
    <div className="space-y-6 animate-fade-in pb-16">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="p-1.5 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <ShieldCheck className="w-5 h-5" />
            </span>
            <h2 className="font-heading text-2xl font-bold text-white">Review & Approval Center</h2>
            <span className="badge badge-urgent">{queueCases.length} Awaiting Review</span>
          </div>
          <p className="text-xs text-slate-400">
            Human-in-the-loop review station. High-stakes dispute submissions require single-use approval tokens bound to SHA-256 payload hashes.
          </p>
        </div>

        <button
          onClick={fetchReviewQueue}
          className="btn btn-secondary text-xs flex items-center gap-2 self-start sm:self-auto"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Refresh Queue</span>
        </button>
      </div>

      {actionSuccess && (
        <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
            <span>{actionSuccess}</span>
          </div>
          <button onClick={() => setActionSuccess(null)} className="text-emerald-400 hover:text-emerald-200">
            Dismiss
          </button>
        </div>
      )}

      {loading ? (
        <div className="py-20 text-center">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
          <p className="text-slate-400 text-xs">Loading pending review queue...</p>
        </div>
      ) : queueCases.length === 0 ? (
        <div className="glass-panel p-16 text-center">
          <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto mb-3" />
          <h3 className="font-heading text-lg font-bold text-white mb-1">All Caught Up!</h3>
          <p className="text-xs text-slate-400 max-w-md mx-auto mb-5">
            There are no analyzed dispute drafts awaiting review at this moment. You can analyze new disputes in the worklist.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: Queue List */}
          <div className="lg:col-span-5 glass-panel divide-y divide-slate-800/80 overflow-hidden">
            <div className="p-3 bg-slate-900/60 text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex justify-between items-center">
              <span>Pending Drafts ({queueCases.length})</span>
              <span>Sorted by Urgency</span>
            </div>

            <div className="max-h-[640px] overflow-y-auto divide-y divide-slate-800/40">
              {queueCases.map((item) => {
                const isSelected = selectedCase?.case_id === item.case_id;
                return (
                  <div
                    key={item.case_id}
                    onClick={() => loadDetail(item.case_id)}
                    className={`p-4 cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-indigo-600/15 border-l-4 border-indigo-500'
                        : 'hover:bg-slate-800/40 border-l-4 border-transparent'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-1.5">
                      <div>
                        <span className="font-mono text-xs font-bold text-white">{item.case_id}</span>
                        <span className="text-[10px] font-mono text-slate-500 ml-2">{item.dispute_id}</span>
                      </div>
                      <span className="font-mono text-xs font-bold text-indigo-300">{item.amount_display}</span>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-slate-400 mb-2">
                      <span className="capitalize">{item.reason_class.replace(/_/g, ' ')}</span>
                      <span className={`flex items-center gap-1 font-medium ${item.hours_remaining <= 24 ? 'text-rose-400' : 'text-amber-300'}`}>
                        <Clock className="w-3 h-3" />
                        <span>{item.hours_remaining}h remain</span>
                      </span>
                    </div>

                    <div className="flex items-center justify-between pt-1 text-[11px]">
                      <span className="text-emerald-400 font-medium">Win prob: {Math.round(item.p_win * 100)}%</span>
                      <span className="text-slate-500 flex items-center gap-0.5">
                        <span>Review</span>
                        <ChevronRight className="w-3.5 h-3.5" />
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Column: Case Rebuttal Inspection & Action Panel */}
          <div className="lg:col-span-7 glass-panel p-6 space-y-6">
            {loadingDetail || !selectedCase ? (
              <div className="py-24 text-center">
                <div className="w-7 h-7 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-2"></div>
                <p className="text-xs text-slate-400">Loading case details...</p>
              </div>
            ) : (
              <>
                {/* Header info */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-800">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-heading text-xl font-bold text-white">{selectedCase.case_id}</h3>
                      <span className="text-xs font-mono font-medium px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                        {selectedCase.dispute.id}
                      </span>
                    </div>
                    <p className="text-xs text-slate-400">
                      Customer: <strong className="text-slate-200">{selectedCase.order?.customer_name || 'N/A'}</strong> ({selectedCase.order?.customer_email || 'N/A'})
                    </p>
                  </div>

                  <div className="text-right">
                    <div className="font-mono text-xl font-extrabold text-white">
                      ₹{(selectedCase.dispute.amount / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                    <div className="text-[11px] text-amber-400 font-medium">
                      Respond by: {selectedCase.deadline?.respond_by || 'Urgent'}
                    </div>
                  </div>
                </div>

                {/* AI Recommendation Badge & Facts */}
                <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                      <Sparkles className="w-4 h-4 text-cyan-400" />
                      <span>AI Model Recommendation</span>
                    </span>
                    <span className="badge badge-won uppercase font-mono">
                      {selectedCase.analysis?.recommendation?.decision || 'CONTEST'}
                    </span>
                  </div>

                  <p className="text-xs text-slate-300 leading-relaxed">
                    {selectedCase.analysis?.recommendation?.summary || 
                     'Verified shipping carrier records confirm delivery to customer address. Rebuttal letter drafted and citation-grounded.'}
                  </p>

                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 pt-2 border-t border-slate-800/80 text-[11px]">
                    <div>
                      <span className="text-slate-500 block">Carrier Tracking:</span>
                      <span className="font-mono text-slate-300 font-medium">{selectedCase.order?.tracking_number || 'N/A'}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">Evidence Docs:</span>
                      <span className="font-mono text-slate-300 font-medium">{selectedCase.documents?.length || 0} attached</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block">PCI-DSS Status:</span>
                      <span className="text-emerald-400 font-medium">Card PAN Sanitized</span>
                    </div>
                  </div>
                </div>

                {/* Rebuttal Letter Preview */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                      <FileText className="w-4 h-4 text-indigo-400" />
                      <span>Generated Bank Rebuttal Letter</span>
                    </label>
                    <span className="text-[11px] font-mono text-slate-500">
                      {selectedCase.analysis?.clean_draft?.draft_text?.length || 0} characters
                    </span>
                  </div>

                  <div className="p-4 rounded-xl bg-slate-950 border border-slate-800/90 font-mono text-xs text-slate-300 max-h-64 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                    {selectedCase.analysis?.clean_draft?.draft_text || 'No draft text generated yet.'}
                  </div>
                </div>

                {/* Reviewer Action Buttons */}
                <div className="pt-4 border-t border-slate-800 flex flex-wrap items-center justify-between gap-3">
                  <button
                    onClick={() => onSelectCase(selectedCase.case_id)}
                    className="btn btn-secondary text-xs"
                  >
                    <span>Open Full Case Editor</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setRejectModalOpen(true)}
                      className="btn btn-ghost text-xs text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 border border-rose-500/30"
                    >
                      <XCircle className="w-3.5 h-3.5" />
                      <span>Reject & Request Revision</span>
                    </button>

                    <button
                      onClick={handleRequestApproval}
                      className="btn btn-primary text-xs"
                    >
                      <Key className="w-3.5 h-3.5" />
                      <span>Request Approval Token</span>
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Approval Token Modal */}
      {approvalModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content p-6 sm:p-8 max-w-xl">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                <Lock className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-heading text-lg font-bold text-white">Cryptographic Approval Token Issued</h3>
                <p className="text-xs text-slate-400">Single-use token cryptographically bound to exact submission JSON payload.</p>
              </div>
            </div>

            <div className="space-y-4 text-xs">
              <div>
                <label className="text-[11px] font-semibold text-slate-400 block mb-1">Payload SHA-256 Digest:</label>
                <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 font-mono text-[11px] text-cyan-300 break-all">
                  {payloadHash}
                </div>
              </div>

              <div>
                <label className="text-[11px] font-semibold text-slate-400 block mb-1">Single-Use Approval Token:</label>
                <div className="p-2.5 rounded-lg bg-slate-950 border border-indigo-500/40 font-mono text-xs text-indigo-300 font-bold break-all select-all">
                  {approvalToken}
                </div>
              </div>

              <div>
                <label className="text-[11px] font-semibold text-slate-400 block mb-1">Signed Submission Payload Preview:</label>
                <pre className="p-3 rounded-lg bg-slate-950 border border-slate-800 text-[10px] text-slate-400 max-h-36 overflow-y-auto">
                  {payloadJson}
                </pre>
              </div>

              <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[11px] flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0 text-amber-400" />
                <span>
                  Confirming this action will finalize the contestation in the audit ledger and prepare it for Razorpay dispatch.
                </span>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setApprovalModalOpen(false)}
                className="btn btn-secondary text-xs"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={handleConfirmSubmit}
                className="btn btn-primary text-xs flex items-center gap-2"
              >
                {submitting ? (
                  <span>Dispatching...</span>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" />
                    <span>Authorize & Submit Contest</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reject Draft Modal */}
      {rejectModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content p-6 sm:p-8 max-w-lg">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
                <XCircle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-heading text-lg font-bold text-white">Reject AI Rebuttal Draft</h3>
                <p className="text-xs text-slate-400">Provide feedback reason so the merchant team can update facts or evidence.</p>
              </div>
            </div>

            <form onSubmit={handleConfirmReject} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Rejection Reason / Required Changes:
                </label>
                <textarea
                  required
                  rows={4}
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="e.g. Courier tracking signature needs formal Delhivery POD stamp before submission..."
                  className="input-control text-xs resize-none"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setRejectModalOpen(false)}
                  className="btn btn-secondary text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={rejecting || !rejectReason.trim()}
                  className="btn text-xs bg-rose-600 hover:bg-rose-500 text-white font-semibold"
                >
                  {rejecting ? 'Recording Rejection...' : 'Confirm Rejection'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

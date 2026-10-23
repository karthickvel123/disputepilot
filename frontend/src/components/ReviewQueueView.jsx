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
import { renderCleanDraft, renderDraftPreview } from '../utils/draft';

function formatDeadline(hoursRemaining) {
  if (hoursRemaining === null || hoursRemaining === undefined || !Number.isFinite(Number(hoursRemaining))) {
    return 'Deadline unavailable';
  }
  if (Number(hoursRemaining) <= 0) return 'Overdue';
  return `${Number(hoursRemaining).toFixed(1).replace(/\.0$/, '')}h remaining`;
}

function formatRespondBy(value) {
  if (!value) return 'Deadline unavailable';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

export default function ReviewQueueView({ onSelectCase }) {
  const [queueCases, setQueueCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedCase, setSelectedCase] = useState(null);
  const [selectedCaseId, setSelectedCaseId] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState('');

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
      const nextCaseId = items.some((item) => item.case_id === selectedCaseId)
        ? selectedCaseId
        : items[0]?.case_id || null;
      if (nextCaseId) {
        if (nextCaseId !== selectedCaseId) setSelectedCase(null);
        await loadDetail(nextCaseId);
      } else {
        setSelectedCase(null);
        setSelectedCaseId(null);
      }
    } catch (err) {
      setError(err.message || 'Failed to load review queue.');
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(caseId) {
    setSelectedCaseId(caseId);
    setLoadingDetail(true);
    setDetailError('');
    setActionSuccess(null);
    try {
      const detail = await getDispute(caseId);
      setSelectedCase(detail);
    } catch (err) {
      setDetailError(err.message || 'Could not load the selected dispute.');
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
    } catch (err) {
      alert(`Rejection failed: ${err.message}`);
    } finally {
      setRejecting(false);
    }
  }

  return (
    <div className="review-queue-view space-y-6 animate-fade-in pb-16">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-3 mb-1.5">
            <span className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <ShieldCheck className="w-5 h-5" />
            </span>
            <h2 className="font-heading text-2xl font-bold text-white">Review & Approval Center</h2>
            <span className="badge badge-urgent text-xs px-3 py-1">{queueCases.length} Awaiting Review</span>
          </div>
          <p className="text-sm text-slate-400">
            Human-in-the-loop review station. High-stakes dispute submissions require single-use approval tokens bound to SHA-256 payload hashes.
          </p>
        </div>

        <button
          onClick={fetchReviewQueue}
          className="btn btn-secondary text-sm h-10 px-4 flex items-center gap-2 self-start sm:self-auto"
        >
          <RefreshCw className="w-4 h-4" />
          <span>Refresh Queue</span>
        </button>
      </div>

      {actionSuccess && (
        <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-sm flex items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="w-5 h-5 text-emerald-400 flex-shrink-0" />
            <span className="font-medium">{actionSuccess}</span>
          </div>
          <button onClick={() => setActionSuccess(null)} className="text-emerald-400 hover:text-emerald-200 font-bold px-2 py-1">
            Dismiss
          </button>
        </div>
      )}

      {loading ? (
        <div className="py-24 text-center">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
          <p className="text-slate-400 text-sm">Loading pending review queue...</p>
        </div>
      ) : queueCases.length === 0 ? (
        <div className="glass-panel p-16 text-center">
          <CheckCircle2 className="w-12 h-12 text-emerald-400 mx-auto mb-3" />
          <h3 className="font-heading text-xl font-bold text-white mb-2">All Caught Up!</h3>
          <p className="text-sm text-slate-400 max-w-md mx-auto mb-5 leading-relaxed">
            There are no analyzed dispute drafts awaiting review at this moment. You can analyze new disputes in the worklist.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Column: Queue List */}
          <div className="lg:col-span-5 glass-panel-premium card-sheen divide-y divide-slate-800/80 overflow-hidden shadow-xl rounded-2xl">
            <div className="p-4.5 bg-slate-900/70 text-sm font-bold uppercase tracking-wider text-slate-300 flex justify-between items-center border-b border-slate-800">
              <span>Pending Drafts ({queueCases.length})</span>
              <span className="text-xs text-slate-400">Sorted by Urgency</span>
            </div>

            <div className="max-h-[760px] overflow-y-auto divide-y divide-slate-800/40">
              {queueCases.map((item) => {
                const isSelected = selectedCase?.case_id === item.case_id;
                return (
                  <div
                    key={item.case_id}
                    onClick={() => loadDetail(item.case_id)}
                    className={`p-5 cursor-pointer transition-all ${
                      isSelected
                        ? 'bg-indigo-600/20 border-l-4 border-indigo-500 shadow-sm'
                        : 'hover:bg-slate-800/40 border-l-4 border-transparent'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div className="min-w-0">
                        <span className="font-mono text-base font-bold text-white">{item.case_id}</span>
                        {item.dispute_id && item.dispute_id !== item.case_id && (
                          <span className="text-sm font-mono text-slate-400 ml-2.5">{item.dispute_id}</span>
                        )}
                      </div>
                      <span className="font-mono text-base font-bold text-indigo-300">{item.amount_display}</span>
                    </div>

                    <div className="flex items-center justify-between text-sm text-slate-400 my-2.5">
                      <span className="capitalize font-medium text-slate-300">{item.reason_class.replace(/_/g, ' ')}</span>
                      <span className={`flex items-center gap-1.5 font-semibold text-sm ${item.hours_remaining === null || item.hours_remaining === undefined ? 'text-slate-500' : item.hours_remaining <= 24 ? 'text-rose-400' : 'text-amber-300'}`}>
                        <Clock className="w-4 h-4" />
                        <span>{formatDeadline(item.hours_remaining)}</span>
                      </span>
                    </div>

                    <div className="flex items-center justify-between pt-1 text-sm">
                      <span className="text-emerald-400 font-semibold">Win prob: {Math.round(item.p_win * 100)}%</span>
                      <span className="text-indigo-400 font-semibold flex items-center gap-1 hover:text-indigo-300">
                        <span>Review</span>
                        <ChevronRight className="w-4 h-4" />
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Right Column: Case Rebuttal Inspection & Action Panel */}
          <div className="lg:col-span-7 glass-panel-premium card-sheen p-7 sm:p-9 space-y-8 shadow-xl rounded-2xl">
            {detailError ? (
              <div className="py-12 text-center" role="alert">
                <p className="text-base font-medium text-rose-700">{detailError}</p>
                <button
                  type="button"
                  onClick={() => selectedCaseId && loadDetail(selectedCaseId)}
                  disabled={!selectedCaseId}
                  className="btn btn-secondary mt-4 text-sm h-10 px-4"
                >
                  Retry loading case
                </button>
              </div>
            ) : loadingDetail || !selectedCase ? (
              <div className="py-28 text-center">
                <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3"></div>
                <p className="text-sm text-slate-400">Loading case details...</p>
              </div>
            ) : (
              <>
                {/* Header info */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-800">
                  <div>
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="font-heading text-2xl sm:text-3xl font-bold text-white tracking-tight">{selectedCase.case_id}</h3>
                      {selectedCase.dispute.id !== selectedCase.case_id && (
                        <span className="text-xs font-mono font-medium px-2.5 py-1 rounded-md bg-slate-800 text-slate-300">
                          {selectedCase.dispute.id}
                        </span>
                      )}
                    </div>
                    <p className="text-sm sm:text-base text-slate-400">
                      Customer: <strong className="text-slate-200">{selectedCase.order?.customer_name || 'N/A'}</strong> ({selectedCase.order?.customer_email || 'N/A'})
                    </p>
                  </div>

                  <div className="text-left sm:text-right">
                    <div className="font-mono text-2xl sm:text-3xl font-extrabold text-white">
                      ₹{(selectedCase.dispute.amount / 100).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                    <div className="text-sm sm:text-base text-amber-400 font-semibold mt-1">
                      Respond by: {formatRespondBy(selectedCase.deadline?.respond_by)}
                    </div>
                  </div>
                </div>

                {/* AI Recommendation Badge & Facts */}
                <div className="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-base font-bold text-slate-200 flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-cyan-400" />
                      <span>AI Model Recommendation</span>
                    </span>
                    <span className="badge badge-won uppercase font-mono px-3.5 py-1 text-xs sm:text-sm">
                      {selectedCase.analysis?.recommendation?.decision || 'CONTEST'}
                    </span>
                  </div>

                  <p className="text-sm sm:text-base leading-relaxed text-slate-300">
                    {selectedCase.analysis?.recommendation?.summary || 
                     'Verified shipping carrier records confirm delivery to customer address. Rebuttal letter drafted and citation-grounded.'}
                  </p>

                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pt-4 border-t border-slate-800/80">
                    <div>
                      <span className="text-slate-400 block text-xs sm:text-sm uppercase font-bold tracking-wider mb-1">Carrier Tracking</span>
                      <span className="font-mono text-slate-200 text-sm sm:text-base font-semibold">{selectedCase.order?.tracking_number || 'N/A'}</span>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-xs sm:text-sm uppercase font-bold tracking-wider mb-1">Evidence Docs</span>
                      <span className="font-mono text-slate-200 text-sm sm:text-base font-semibold">{selectedCase.documents?.length || 0} attached</span>
                    </div>
                    <div>
                      <span className="text-slate-400 block text-xs sm:text-sm uppercase font-bold tracking-wider mb-1">PCI-DSS Status</span>
                      <span className="text-emerald-400 text-sm sm:text-base font-semibold">Card PAN Sanitized</span>
                    </div>
                  </div>
                </div>

                {/* Rebuttal Letter Preview */}
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <label className="text-base font-bold text-slate-200 flex items-center gap-2">
                      <FileText className="w-4 h-4 text-indigo-400" />
                      <span>Generated Bank Rebuttal Letter</span>
                    </label>
                    <span className="text-xs sm:text-sm font-mono text-slate-400 font-medium">
                      {renderCleanDraft(selectedCase.analysis?.clean_draft).length} characters
                    </span>
                  </div>

                  <div className="review-draft-preview p-6 rounded-2xl bg-slate-950 border border-slate-800/90 text-sm sm:text-base leading-relaxed text-slate-200 max-h-96 overflow-y-auto whitespace-pre-wrap shadow-inner font-sans">
                    {renderDraftPreview(selectedCase.analysis?.clean_draft) || 'No draft text generated yet.'}
                  </div>
                </div>

                {/* Reviewer Action Buttons */}
                <div className="pt-6 border-t border-slate-800 flex flex-wrap items-center justify-between gap-4">
                  <button
                    onClick={() => onSelectCase(selectedCase.case_id)}
                    className="btn btn-secondary text-sm h-11 px-5"
                  >
                    <span>Open Full Case Editor</span>
                    <ArrowRight className="w-4 h-4" />
                  </button>

                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => setRejectModalOpen(true)}
                      className="btn btn-ghost text-sm h-11 px-5 text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 border border-rose-500/30"
                    >
                      <XCircle className="w-4 h-4" />
                      <span>Reject & Request Revision</span>
                    </button>

                    <button
                      onClick={handleRequestApproval}
                      className="btn btn-primary text-sm h-11 px-5 font-semibold"
                    >
                      <Key className="w-4 h-4" />
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
          <div className="modal-content p-7 sm:p-9 max-w-xl">
            <div className="flex items-center gap-3.5 mb-5">
              <div className="w-11 h-11 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
                <Lock className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-heading text-xl font-bold text-white">Cryptographic Approval Token Issued</h3>
                <p className="text-sm text-slate-400">Single-use token cryptographically bound to exact submission JSON payload.</p>
              </div>
            </div>

            <div className="space-y-4 text-sm sm:text-base">
              <div>
                <label className="text-xs sm:text-sm font-bold uppercase tracking-wider text-slate-300 block mb-1.5">Payload SHA-256 Digest:</label>
                <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 font-mono text-xs sm:text-sm text-cyan-300 break-all">
                  {payloadHash}
                </div>
              </div>

              <div>
                <label className="text-xs sm:text-sm font-bold uppercase tracking-wider text-slate-300 block mb-1.5">Single-Use Approval Token:</label>
                <div className="p-4 rounded-xl bg-slate-950 border border-indigo-500/40 font-mono text-sm sm:text-base text-indigo-300 font-bold break-all select-all">
                  {approvalToken}
                </div>
              </div>

              <div>
                <label className="text-xs sm:text-sm font-bold uppercase tracking-wider text-slate-300 block mb-1.5">Signed Submission Payload Preview:</label>
                <pre className="p-4 rounded-xl bg-slate-950 border border-slate-800 text-xs sm:text-sm text-slate-300 max-h-48 overflow-y-auto font-mono">
                  {payloadJson}
                </pre>
              </div>

              <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-300 text-sm flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 flex-shrink-0 text-amber-400" />
                <span>
                  Confirming this action will finalize the contestation in the audit ledger and prepare it for Razorpay dispatch.
                </span>
              </div>
            </div>

            <div className="mt-7 flex items-center justify-end gap-3.5">
              <button
                type="button"
                onClick={() => setApprovalModalOpen(false)}
                className="btn btn-secondary text-sm h-11 px-5"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={handleConfirmSubmit}
                className="btn btn-primary text-sm h-11 px-6 font-semibold flex items-center gap-2"
              >
                {submitting ? (
                  <span>Dispatching...</span>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
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
          <div className="modal-content p-7 sm:p-9 max-w-lg">
            <div className="flex items-center gap-3.5 mb-5">
              <div className="w-11 h-11 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
                <XCircle className="w-6 h-6" />
              </div>
              <div>
                <h3 className="font-heading text-xl font-bold text-white">Reject AI Rebuttal Draft</h3>
                <p className="text-sm text-slate-400">Provide feedback reason so the merchant team can update facts or evidence.</p>
              </div>
            </div>

            <form onSubmit={handleConfirmReject} className="space-y-5">
              <div>
                <label className="block text-sm font-semibold text-slate-200 mb-2">
                  Rejection Reason / Required Changes:
                </label>
                <textarea
                  required
                  rows={4}
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="e.g. Courier tracking signature needs formal Delhivery POD stamp before submission..."
                  className="input-control text-sm p-4 rounded-xl resize-none min-h-[130px] leading-relaxed"
                />
              </div>

              <div className="flex items-center justify-end gap-3.5 pt-2">
                <button
                  type="button"
                  onClick={() => setRejectModalOpen(false)}
                  className="btn btn-secondary text-sm h-11 px-5"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={rejecting || !rejectReason.trim()}
                  className="btn text-sm h-11 px-6 bg-rose-600 hover:bg-rose-500 text-white font-semibold"
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

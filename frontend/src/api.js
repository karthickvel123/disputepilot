// In production, prefer the deployed Render API even when Vercel's env var is missing.
// VITE_API_BASE_URL should still be configured in Vercel for environment-specific deployments.
const DEFAULT_PRODUCTION_API = 'https://disputepilot.onrender.com/api/v1';
const API_BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.PROD ? DEFAULT_PRODUCTION_API : '/api/v1')
).replace(/\/+$/, '');

let currentCsrfToken = '';

export function setCsrfToken(token) {
  currentCsrfToken = token || '';
}

export function getCsrfToken() {
  return currentCsrfToken;
}

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const headers = {
    'Accept': 'application/json',
    ...(options.headers || {}),
  };

  if (currentCsrfToken && !headers['x-csrf-token']) {
    headers['x-csrf-token'] = currentCsrfToken;
  }

  const config = {
    ...options,
    headers,
    credentials: 'include', // sends and receives cookies
  };

  let response;
  try {
    response = await fetch(url, config);
  } catch (cause) {
    const err = new Error(
      `Unable to reach the DisputePilot API at ${API_BASE}. Check the backend URL, backend health, and CORS settings.`,
      { cause }
    );
    err.status = 0;
    err.data = { detail: err.message };
    throw err;
  }

  if (response.status === 401 && endpoint !== '/auth/login' && endpoint !== '/auth/me') {
    window.dispatchEvent(new CustomEvent('auth:unauthorized'));
  }

  const contentType = response.headers.get('content-type') || '';
  let data = null;
  if (contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch (cause) {
      const err = new Error(`The API returned invalid JSON for '${endpoint}'.` , { cause });
      err.status = 502;
      err.data = { detail: err.message };
      throw err;
    }
  } else {
    const rawText = await response.text();
    if (rawText.trim().toLowerCase().startsWith('<!doctype') || rawText.trim().toLowerCase().startsWith('<html')) {
      const deployErr = new Error(
        `Backend API routing mismatch: Received HTML instead of JSON for '${endpoint}'. ` +
        `Ensure VITE_API_BASE_URL is set in your environment pointing to the actual backend API server.`
      );
      deployErr.status = 502;
      deployErr.data = { detail: deployErr.message };
      throw deployErr;
    }
    data = { detail: rawText };
  }

  if (!response.ok) {
    const errorMsg = data?.detail || data?.message || `HTTP ${response.status} Error`;
    const err = new Error(errorMsg);
    err.status = response.status;
    err.data = data;
    throw err;
  }

  return data;
}

// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------

export async function login(username, password) {
  const data = await request('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (data?.csrf_token) {
    setCsrfToken(data.csrf_token);
  }
  return data;
}

export async function logout() {
  const data = await request('/auth/logout', { method: 'POST' });
  setCsrfToken('');
  return data;
}

export async function getMe() {
  const data = await request('/auth/me');
  if (data?.csrf_token) {
    setCsrfToken(data.csrf_token);
  }
  return data;
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export async function getDashboardMetrics() {
  return request('/dashboard/metrics');
}

// ---------------------------------------------------------------------------
// Disputes
// ---------------------------------------------------------------------------

export async function listDisputes({
  page = 1,
  per_page = 25,
  status_filter = 'all',
  reason_filter = 'all',
  search = '',
} = {}) {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(per_page),
    ...(status_filter && status_filter !== 'all' ? { status_filter } : {}),
    ...(reason_filter && reason_filter !== 'all' ? { reason_filter } : {}),
    ...(search ? { search } : {}),
  });
  return request(`/disputes?${params.toString()}`);
}

export async function getDispute(caseId) {
  return request(`/disputes/${encodeURIComponent(caseId)}`);
}

export async function analyzeDispute(caseId) {
  return request(`/disputes/${encodeURIComponent(caseId)}/analyze`, {
    method: 'POST',
  });
}

export async function saveDraft(caseId, summary) {
  return request(`/disputes/${encodeURIComponent(caseId)}/draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ summary, csrf_token: currentCsrfToken }),
  });
}

// ---------------------------------------------------------------------------
// Approval & Submission
// ---------------------------------------------------------------------------

export async function requestContestApproval(caseId) {
  return request(`/disputes/${encodeURIComponent(caseId)}/request-approval`, {
    method: 'POST',
  });
}

export async function submitContest(caseId, approvalToken, payloadHash) {
  return request(`/disputes/${encodeURIComponent(caseId)}/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      approval_token: approvalToken,
      payload_hash: payloadHash,
      csrf_token: currentCsrfToken,
    }),
  });
}

export async function requestAccept(caseId, typedAmount) {
  return request(`/disputes/${encodeURIComponent(caseId)}/request-accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      typed_amount: String(typedAmount),
      csrf_token: currentCsrfToken,
    }),
  });
}

export async function acceptDispute(caseId, approvalToken, payloadHash) {
  return request(`/disputes/${encodeURIComponent(caseId)}/accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      approval_token: approvalToken,
      payload_hash: payloadHash,
      csrf_token: currentCsrfToken,
    }),
  });
}

// ---------------------------------------------------------------------------
// Evidence Upload
// ---------------------------------------------------------------------------

export async function uploadEvidence(caseId, { file, category, attestNoCardData, excerpt }) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('category', category);
  formData.append('attest_no_card_data', attestNoCardData ? 'yes' : 'no');
  if (excerpt) {
    formData.append('excerpt', excerpt);
  }
  formData.append('csrf_token', currentCsrfToken);

  return request(`/disputes/${encodeURIComponent(caseId)}/evidence`, {
    method: 'POST',
    body: formData,
  });
}

// ---------------------------------------------------------------------------
// Audit Ledger
// ---------------------------------------------------------------------------

export async function getCaseAudit(caseId) {
  return request(`/disputes/${encodeURIComponent(caseId)}/audit`);
}

export async function getGlobalAudit(page = 1, perPage = 50) {
  return request(`/audit?page=${page}&per_page=${perPage}`);
}

export async function verifyAuditLedger() {
  return request('/audit/verify');
}

// ---------------------------------------------------------------------------
// System & Settings
// ---------------------------------------------------------------------------

export async function getSettings() {
  return request('/settings');
}

export async function getHealth() {
  return request('/health');
}

// ---------------------------------------------------------------------------
// SaaS Identity & User Management
// ---------------------------------------------------------------------------

export async function registerUser({ username, password, full_name, role = 'reviewer' }) {
  const data = await request('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, full_name, role }),
  });
  if (data?.csrf_token) {
    setCsrfToken(data.csrf_token);
  }
  return data;
}

export async function register(usernameOrObj, password, full_name, role = 'reviewer') {
  if (typeof usernameOrObj === 'object' && usernameOrObj !== null) {
    return registerUser(usernameOrObj);
  }
  return registerUser({ username: usernameOrObj, password, full_name, role });
}

export async function changePassword({ old_password, new_password }) {
  return request('/auth/change-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ old_password, new_password }),
  });
}

export async function listUsers() {
  return request('/auth/users');
}

export async function updateUserRole(username, role) {
  return request(`/auth/users/${encodeURIComponent(username)}/role`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  });
}

// ---------------------------------------------------------------------------
// Dispute Operations & Batch Imports
// ---------------------------------------------------------------------------

export async function createDispute(disputeData) {
  return request('/disputes/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(disputeData),
  });
}

export async function importDisputesCsv({ csv_data, dry_run = true }) {
  return request('/disputes/import-csv', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ csv_data, dry_run }),
  });
}

export function getDisputesExportUrl() {
  return `${API_BASE}/disputes/export`;
}

// ---------------------------------------------------------------------------
// Reviewer Collaboration & Rejection
// ---------------------------------------------------------------------------

export async function getComments(caseId) {
  return request(`/disputes/${encodeURIComponent(caseId)}/comments`);
}

export async function addComment(caseId, comment) {
  return request(`/disputes/${encodeURIComponent(caseId)}/comments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comment }),
  });
}

export async function rejectDraft(caseId, reason) {
  return request(`/disputes/${encodeURIComponent(caseId)}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
}

// ---------------------------------------------------------------------------
// Evidence Management & Downloads
// ---------------------------------------------------------------------------

export function getEvidenceDownloadUrl(caseId, docId) {
  return `${API_BASE}/disputes/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(docId)}/download`;
}

export async function deleteEvidence(caseId, docId) {
  return request(`/disputes/${encodeURIComponent(caseId)}/evidence/${encodeURIComponent(docId)}`, {
    method: 'DELETE',
  });
}

// ---------------------------------------------------------------------------
// In-App Notifications
// ---------------------------------------------------------------------------

export async function getNotifications() {
  return request('/notifications');
}

export async function markNotificationRead(notifId) {
  return request(`/notifications/${encodeURIComponent(notifId)}/read`, {
    method: 'POST',
  });
}

// ---------------------------------------------------------------------------
// Organization Profile & Integration Diagnostics
// ---------------------------------------------------------------------------

export async function getOrgSettings() {
  return request('/settings/org');
}

export async function saveOrgSettings(settings) {
  return request('/settings/org', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
}

export async function testRazorpayConnection() {
  return request('/integrations/razorpay/test', {
    method: 'POST',
  });
}

export async function testAiConnection() {
  return request('/integrations/ai/test', {
    method: 'POST',
  });
}


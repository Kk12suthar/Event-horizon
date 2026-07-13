import type { ChartWidget, FolderStatus, GeneratedReport, ProjectStatus, UserRole } from '@/types';

type JsonRecord = Record<string, unknown>;
type ApiBody = JsonRecord | unknown[] | string | number | boolean | null;

interface ApiFetchOptions extends Omit<RequestInit, 'body'> {
  body?: BodyInit | ApiBody;
  skipAuth?: boolean;
}

interface AuthSignInResponse {
  success?: boolean;
  message?: string;
  detail?: string;
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  user?: {
    uid?: string;
    email?: string;
  };
}

interface UserByEmailResponse {
  data?: JsonRecord;
  message?: string;
  detail?: string;
}

export interface AuthSessionPayload {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  firebaseUid?: string;
  firebaseEmail?: string;
  backendUser: JsonRecord;
}

export interface SseStreamHandlers {
  onEvent: (event: JsonRecord) => void;
  onError?: (error: Error) => void;
}


export interface AgentModelConfig {
  provider: string;
  model: string;
  resolved_model: string;
  key_env?: string;
  key_configured: boolean;
  base_url?: string;
  site_url?: string;
  app_name?: string;
  temperature?: number;
}

export interface UpdateAgentModelConfigInput {
  provider: string;
  model: string;
  api_key?: string;
  base_url?: string;
  site_url?: string;
  app_name?: string;
  temperature?: number;
}
export interface TablePreviewResponse {
  columns?: string[];
  data?: Array<Record<string, string | number>>;
  total?: number;
  page?: number;
  limit?: number;
}

export interface PreparedTableDetail {
  id: string;
  name: string;
  source: 'agent_created';
  revision: number;
  row_count: number;
  columns: Array<string | { name?: string }>;
  source_tables: string[];
  recipe: string[];
  active: boolean;
  session_id: string;
  created_at: string;
}

export interface WorkspaceSnapshotResponse {
  session_id: string;
  folder_id: string;
  workspace: {
    selected_table_id?: string | null;
    selected_table_name?: string | null;
    transform_revision?: number;
    transform_status?: string;
  };
  selected_table?: PreparedTableDetail | null;
  transform_tables: PreparedTableDetail[];
  charts: ChartWidget[];
  reports: GeneratedReport[];
  report_drafts?: Array<Record<string, unknown>>;
}
const trimTrailingSlash = (value: string) => value.replace(/\/+$/, '');

export const BACKEND_URL = trimTrailingSlash(
  import.meta.env.VITE_BACKEND_URL || 'http://127.0.0.1:8001',
);
export const API_BASE_URL = `${BACKEND_URL}/api/v1`;
export const AGENT_URL = trimTrailingSlash(
  import.meta.env.VITE_AGENT_URL || 'http://127.0.0.1:8010',
);
export const USING_LANGGRAPH_AGENT = true;
export const DEV_GMAIL_SIGNIN_ENABLED =
  import.meta.env.DEV && import.meta.env.VITE_ENABLE_DEV_GMAIL_SIGNIN === 'true';

const toRecord = (value: unknown): JsonRecord => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as JsonRecord;
  }
  return {};
};

const formatMysqlDate = (date = new Date()) => date.toISOString().slice(0, 19).replace('T', ' ');

export const createId = () => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID().replace(/-/g, '');
  }
  return `${Date.now()}${Math.random().toString(16).slice(2)}`.replace(/\W/g, '');
};

export const isDevGmailSignInEnabled = () => DEV_GMAIL_SIGNIN_ENABLED;

const isGmailAddress = (email: string) => {
  const domain = email.trim().toLowerCase().split('@')[1];
  return domain === 'gmail.com' || domain === 'googlemail.com';
};

const canUseDevGmailSignIn = (email: string, password: string) =>
  DEV_GMAIL_SIGNIN_ENABLED && isGmailAddress(email) && password.trim().length > 0;

const formatDevName = (email: string) => {
  const localPart = email.split('@')[0] || 'gmail-user';
  return localPart
    .replace(/[._-]+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((part) => `${part[0]?.toUpperCase() || ''}${part.slice(1)}`)
    .join(' ') || 'Gmail User';
};

const createDevGmailSession = (email: string): AuthSessionPayload => {
  const normalizedEmail = email.trim().toLowerCase();
  const userId = `dev-gmail-${normalizedEmail.replace(/[^a-z0-9]+/g, '-')}`;

  return {
    accessToken: `dev-gmail-access-${createId()}`,
    refreshToken: `dev-gmail-refresh-${createId()}`,
    expiresIn: 8 * 60 * 60,
    firebaseUid: userId,
    firebaseEmail: normalizedEmail,
    backendUser: {
      id: userId,
      uid: userId,
      name: formatDevName(normalizedEmail),
      email: normalizedEmail,
      role: 'ADMIN',
      status: 'active',
      created_at: formatMysqlDate(),
      auth_provider: 'dev-gmail',
    },
  };
};

export const normalizeRole = (role: unknown): UserRole => {
  const value = String(role || '').toLowerCase();
  if (value.includes('admin')) return 'Admin';
  if (value.includes('analyst') || value.includes('write')) return 'Analyst';
  return 'Viewer';
};

export const normalizeProjectStatus = (status: unknown): ProjectStatus => {
  const value = String(status || 'ACTIVE').toUpperCase();
  if (value === 'ARCHIVED') return 'Archived';
  if (value === 'PUBLISHED') return 'Published';
  if (value === 'DELETED') return 'Deleted';
  return 'Active';
};

export const normalizeFolderStatus = (status: unknown): FolderStatus => {
  const value = String(status || 'ACTIVE').toUpperCase();
  if (value === 'ARCHIVED') return 'Archived';
  if (value === 'DELETED') return 'Deleted';
  return 'Active';
};

export const toBackendStatus = (status?: ProjectStatus | FolderStatus) =>
  String(status || 'Active').toUpperCase();

export const unwrapData = <T>(value: unknown): T => {
  const record = toRecord(value);
  if ('data' in record && record.data !== undefined && record.data !== null) {
    return record.data as T;
  }
  return value as T;
};

const getAccessToken = () => sessionStorage.getItem('access_token');
const getRefreshToken = () => sessionStorage.getItem('refresh_token');
const isFrontendOnlyDevAccessToken = (token: string | null) =>
  DEV_GMAIL_SIGNIN_ENABLED && Boolean(token?.startsWith('dev-gmail-access-'));

export const getAuthHeaders = (): Record<string, string> => {
  const token = getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
};

const readJson = async <T>(response: Response): Promise<T> => {
  const text = await response.text();
  if (!text) return {} as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    return { message: text } as T;
  }
};

const buildUrl = (url: string) => {
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  return `${API_BASE_URL}${url.startsWith('/') ? url : `/${url}`}`;
};

const normalizeBody = (body: ApiFetchOptions['body'], headers: Headers) => {
  if (body === undefined) return undefined;
  if (body instanceof FormData || body instanceof Blob || body instanceof ArrayBuffer) {
    return body;
  }
  if (typeof body === 'string') return body;
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  return JSON.stringify(body);
};

const refreshAccessToken = async () => {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;

  const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) return null;

  const data = await readJson<AuthSignInResponse>(response);
  if (!data.access_token) return null;

  sessionStorage.setItem('access_token', data.access_token);
  if (data.refresh_token) sessionStorage.setItem('refresh_token', data.refresh_token);
  if (data.expires_in) {
    sessionStorage.setItem('token_expiry', String(Date.now() + data.expires_in * 1000));
    sessionStorage.setItem('inactivity_timeout_ms', String(data.expires_in * 1000));
  }
  sessionStorage.setItem('last_activity', String(Date.now()));
  return data.access_token;
};

export const clearStoredAuth = () => {
  sessionStorage.removeItem('access_token');
  sessionStorage.removeItem('refresh_token');
  sessionStorage.removeItem('token_expiry');
  sessionStorage.removeItem('inactivity_timeout_ms');
  sessionStorage.removeItem('last_activity');
  sessionStorage.removeItem('user');
  sessionStorage.removeItem('userId');
  sessionStorage.removeItem('firebaseUid');
};

let redirectingToSignIn = false;

const redirectToSignIn = () => {
  clearStoredAuth();
  if (redirectingToSignIn) return;
  if (window.location.pathname === '/signin') return;
  redirectingToSignIn = true;
  window.location.href = '/signin';
};

export async function apiFetch<T>(url: string, options: ApiFetchOptions = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers);
  const token = options.skipAuth ? null : getAccessToken();

  // The frontend-only Gmail dev session token is never a real JWT and the
  // backend will always reject it with 401 ("Not enough segments"). Fail
  // fast locally instead of round-tripping to the backend and clear the
  // stale session so the user is routed back to sign-in immediately.
  if (token && isFrontendOnlyDevAccessToken(token)) {
    redirectToSignIn();
    throw new Error('Backend rejected the frontend-only Gmail dev session. Start the backend with ENABLE_DEV_GMAIL_SIGNIN=true for API-backed local Gmail testing.');
  }

  if (token && !headers.has('Authorization')) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(buildUrl(url), {
    ...options,
    headers,
    body: normalizeBody(options.body, headers),
  });

  if (response.status === 401 && retry && !options.skipAuth) {
    const newToken = await refreshAccessToken();
    if (newToken) return apiFetch<T>(url, options, false);
    redirectToSignIn();
  }

  if (!response.ok) {
    const errorData = await readJson<JsonRecord>(response);
    const detail = errorData.detail || errorData.message || `HTTP ${response.status}`;
    throw new Error(String(detail));
  }

  return readJson<T>(response);
}

export const apiGet = <T>(url: string, params?: Record<string, string | number | boolean | null | undefined>) => {
  if (!params) return apiFetch<T>(url);
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) search.set(key, String(value));
  });
  const delimiter = url.includes('?') ? '&' : '?';
  return apiFetch<T>(`${url}${delimiter}${search.toString()}`);
};

export const apiPost = <T>(url: string, body: ApiBody) => apiFetch<T>(url, { method: 'POST', body });
export const apiPut = <T>(url: string, body: ApiBody) => apiFetch<T>(url, { method: 'PUT', body });
export const apiDelete = <T>(url: string, body: ApiBody) => apiFetch<T>(url, { method: 'DELETE', body });

export async function signInRequest(email: string, password: string): Promise<AuthSessionPayload> {
  const normalizedEmail = email.trim().toLowerCase();
  let response: Response;

  try {
    response = await fetch(`${API_BASE_URL}/auth/signin`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: normalizedEmail, password }),
    });
  } catch (error) {
    if (canUseDevGmailSignIn(normalizedEmail, password)) {
      return createDevGmailSession(normalizedEmail);
    }
    throw error;
  }

  const data = await readJson<AuthSignInResponse>(response);

  // Note: the client-only dev-gmail fallback only triggers when the backend
  // itself is unreachable (see the network-error catch block above). A
  // reachable backend that rejects sign-in (wrong credentials, dev-gmail
  // disabled, etc.) must surface a real error instead of silently minting a
  // fake local session that the backend will never recognize.
  if (!response.ok || !data.access_token || !data.refresh_token) {
    throw new Error(data.detail || data.message || 'Sign-in failed');
  }

  const userResponse = await fetch(`${API_BASE_URL}/user/getUserByEmail/${encodeURIComponent(normalizedEmail)}`, {
    headers: {
      Authorization: `Bearer ${data.access_token}`,
      'Content-Type': 'application/json',
    },
  });
  const userData = await readJson<UserByEmailResponse>(userResponse);
  if (!userResponse.ok || !userData.data) {
    throw new Error(userData.detail || userData.message || 'Failed to fetch user details');
  }

  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresIn: data.expires_in || 1800,
    firebaseUid: data.user?.uid,
    firebaseEmail: data.user?.email,
    backendUser: userData.data,
  };
}

export async function signUpRequest(name: string, email: string, password: string) {
  const response = await fetch(`${API_BASE_URL}/auth/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, full_name: name, plan: 'pro' }),
  });
  const data = await readJson<JsonRecord>(response);
  if (!response.ok) throw new Error(String(data.detail || data.message || 'Sign-up failed'));
  return data;
}

export async function logoutRequest() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return;
  await fetch(`${API_BASE_URL}/auth/logout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  }).catch(() => undefined);
}

export const forgotPasswordRequest = (email: string) =>
  apiFetch<JsonRecord>('/auth/forgot-password', { method: 'POST', body: { email }, skipAuth: true });

export const resetPasswordRequest = (oobCode: string, newPassword: string) =>
  apiFetch<JsonRecord>('/auth/reset-password', {
    method: 'POST',
    body: { oob_code: oobCode, new_password: newPassword },
    skipAuth: true,
  });

export const verifyEmailRequest = (oobCode: string) =>
  apiFetch<JsonRecord>(`/auth/verify-email?oobCode=${encodeURIComponent(oobCode)}`, { skipAuth: true });

export const fetchProjectsForUser = (userId: string) =>
  apiGet<unknown[]>(`/project/getProjectByUser/${userId}`);

export async function createProjectRecord(input: {
  id?: string;
  name: string;
  description: string;
  createdBy: string;
  status?: ProjectStatus;
}) {
  const id = input.id || createId();
  const createdAt = formatMysqlDate();
  const payload = {
    id,
    name: input.name,
    description: input.description,
    created_by: input.createdBy,
    created_at: createdAt,
    status: toBackendStatus(input.status),
  };
  await apiPost<JsonRecord>('/project/createProject', payload);

  const expiration = new Date();
  expiration.setFullYear(expiration.getFullYear() + 10);
  await apiPost<JsonRecord>('/project/grantProjectAccess', {
    entity_id: id,
    entity_type: 'PROJECT',
    user_id: input.createdBy,
    access_level: 'ADMIN',
    access_granted_date: createdAt,
    access_granted_by: input.createdBy,
    access_expiration_date: formatMysqlDate(expiration),
  }).catch(() => undefined);

  return { ...payload, folders: [], users: [], user_access_level: 'ADMIN' };
}

export const updateProjectRecord = (id: string, updates: { name?: string; description?: string; status?: ProjectStatus }) =>
  apiPut<JsonRecord>('/project/editProject', {
    id,
    ...(updates.name !== undefined ? { name: updates.name } : {}),
    ...(updates.description !== undefined ? { description: updates.description } : {}),
    ...(updates.status !== undefined ? { status: toBackendStatus(updates.status) } : {}),
  });

export const deleteProjectRecord = (id: string) => apiDelete<JsonRecord>('/project/deleteProject', { id });

export async function createFolderRecord(input: {
  id?: string;
  name: string;
  description: string;
  projectId: string;
  createdBy: string;
  status?: FolderStatus;
}) {
  const payload = {
    id: input.id || createId(),
    name: input.name,
    description: input.description,
    created_at: formatMysqlDate(),
    created_by: input.createdBy,
    status: toBackendStatus(input.status),
    project_id: input.projectId,
    entities: null,
  };
  await apiPost<JsonRecord>('/folder/createFolder', payload);
  return payload;
}

export const updateFolderRecord = (id: string, updates: { name?: string; description?: string; status?: FolderStatus; entities?: unknown }) =>
  apiPut<JsonRecord>('/folder/editFolder', {
    id,
    ...(updates.name !== undefined ? { name: updates.name } : {}),
    ...(updates.description !== undefined ? { description: updates.description } : {}),
    ...(updates.status !== undefined ? { status: toBackendStatus(updates.status) } : {}),
    ...(updates.entities !== undefined ? { entities: updates.entities } : {}),
  });

export const deleteFolderRecord = (id: string) => apiPut<JsonRecord>('/folder/deleteFolder', { id });
export const fetchFolderById = (id: string) => apiGet<unknown>(`/folder/getFolder/${id}`);

export const fetchSessionByFolderAndUser = (folderId: string, userId: string) =>
  apiGet<unknown>(`/session/getSessionByFolderAndUser/${folderId}/${userId}`);

export async function createSessionRecord(input: {
  id?: string;
  folderId: string;
  appName?: string;
  createdBy: string;
}) {
  const payload = {
    id: input.id || createId(),
    folder_id: input.folderId,
    app_name: input.appName || 'eventhorizon-app',
    created_at: formatMysqlDate(),
    created_by: input.createdBy,
    status: 'ACTIVE',
  };
  await apiPost<JsonRecord>('/session/createSession', payload);
  return payload;
}

export const updateSessionRecord = (id: string, updates: { status?: string; entities?: unknown }) =>
  apiPut<JsonRecord>('/session/editSession', { id, ...updates });

export const createFileRecord = (input: {
  id: string;
  name: string;
  originalName: string;
  uploadedBy: string;
  parentFolderId: string;
  status?: 'UPLOADED' | 'PROCESSED' | 'FAILED';
}) =>
  apiPost<JsonRecord>('/file/createFile', {
    id: input.id,
    name: input.name,
    originalName: input.originalName,
    created_at: formatMysqlDate(),
    uploaded_by: input.uploadedBy,
    status: input.status || 'UPLOADED',
    parent_folder_id: input.parentFolderId,
  });

export const updateFileStatus = (id: string, status: 'UPLOADED' | 'PROCESSED' | 'FAILED') =>
  apiPut<JsonRecord>('/file/editFile', { id, status });

export const fetchAllFolderTables = (folderId: string) =>
  apiGet<{
    tables?: Record<string, string>;
    table_types?: Record<string, 'uploaded' | 'agent_created'>;
    table_details?: PreparedTableDetail[];
  }>(`/data/getAllFolderTables/${folderId}`);

export async function fetchSessionWorkspace(sessionId: string, folderId: string) {
  const response = await apiGet<unknown>(`/session/getWorkspace/${sessionId}`, { folder_id: folderId });
  return unwrapData<WorkspaceSnapshotResponse>(response);
}

export async function selectSessionTransform(sessionId: string, folderId: string, tableId: string) {
  const response = await apiPut<unknown>('/session/selectTransform', {
    session_id: sessionId,
    folder_id: folderId,
    table_id: tableId,
  });
  return unwrapData<PreparedTableDetail>(response);
}

export async function saveSessionArtifact<T extends ChartWidget | GeneratedReport>(
  sessionId: string,
  folderId: string,
  artifact: T,
) {
  const response = await apiPut<unknown>('/session/saveArtifact', {
    session_id: sessionId,
    folder_id: folderId,
    artifact,
  });
  return unwrapData<T>(response);
}

export const deleteSessionArtifact = (sessionId: string, folderId: string, artifactId: string) =>
  apiDelete<unknown>('/session/deleteArtifact', {
    session_id: sessionId,
    folder_id: folderId,
    artifact_id: artifactId,
  });
export const fetchTablePreview = (input: {
  tableName: string;
  conversationId: string;
  userId: string;
  pageNo?: number;
  limitNo?: number;
  folderId?: string;
}) =>
  apiPost<TablePreviewResponse>('/data/getTableData', {
    tableName: input.tableName,
    conversationId: input.conversationId,
    userId: input.userId,
    pageNo: input.pageNo || 1,
    limitNo: input.limitNo || 50,
    folderId: input.folderId ? input.folderId.replace(/-/g, '').toLowerCase() : null,
  });

export const getUploadWebSocketUrl = () => `${BACKEND_URL.replace(/^http/, 'ws')}/api/v1/webSockets/file-upload`;

export const getAgentStreamUrl = (surface: 'transform' | 'dashboard') =>
  `${AGENT_URL}${surface === 'dashboard' ? '/agent/dashboard/stream' : '/agent/chat/stream'}`;

export const getReportStreamUrl = (folderId: string) =>
  `${AGENT_URL}/report/chat/stream?folder_id=${encodeURIComponent(folderId)}`;

export const activateTransformRunner = async (folderId: string, sessionId: string) =>
  ({ status: 'ready', folder_id: folderId, session_id: sessionId });

export const fetchAgentModelConfig = () =>
  apiFetch<AgentModelConfig>(`${AGENT_URL}/agent/model-config`);

export const updateAgentModelConfig = (body: UpdateAgentModelConfigInput) =>
  apiFetch<AgentModelConfig>(`${AGENT_URL}/agent/model-config`, {
    method: 'PUT',
    body: body as unknown as JsonRecord,
  });

export const activateDashboard = async (sessionId: string, folderId?: string) =>
  apiFetch<JsonRecord>(`${AGENT_URL}/agent/dashboard/activate`, {
    method: 'POST',
    body: { session_id: sessionId, folder_id: folderId },
  });
export async function streamSse(url: string, body: JsonRecord, handlers: SseStreamHandlers, signal?: AbortSignal) {
  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        ...getAuthHeaders(),
      },
      body: JSON.stringify(body),
      signal,
    });

    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new Error(text || `HTTP ${response.status}`);
    }
    if (!response.body) throw new Error('ReadableStream is not supported in this browser');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    const flushEvent = (rawEvent: string) => {
      const data = rawEvent
        .split('\n')
        .map((line) => line.trim())
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n');
      if (!data) return;
      try {
        handlers.onEvent(toRecord(JSON.parse(data)));
      } catch (error) {
        handlers.onError?.(error instanceof Error ? error : new Error(String(error)));
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split(/\r?\n\r?\n/);
      buffer = events.pop() || '';
      events.forEach(flushEvent);
    }

    const tail = buffer.trim();
    if (tail) flushEvent(tail);
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') return;
    const normalized = error instanceof Error ? error : new Error(String(error));
    if (handlers.onError) handlers.onError(normalized);
    else throw normalized;
  }
}
export const downloadBlob = async (url: string, filename: string) => {
  const response = await fetch(url, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error('Download failed');
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(objectUrl);
};

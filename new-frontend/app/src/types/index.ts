// User and Role types
export type UserRole = 'Admin' | 'Analyst' | 'Viewer';

export interface User {
  id: string;
  uid?: string;
  name: string;
  email: string;
  role: UserRole;
  status: 'active' | 'inactive';
  createdAt: string;
  raw?: unknown;
}

// Project types
export type ProjectStatus = 'Active' | 'Archived' | 'Published' | 'Deleted';

export interface Project {
  id: string;
  name: string;
  description: string;
  status: ProjectStatus;
  createdBy: string;
  createdAt: string;
  folderCount: number;
  accessLevel?: string;
  raw?: unknown;
}

// Folder types
export type FolderStatus = 'Active' | 'Archived' | 'Deleted';

export interface Folder {
  id: string;
  name: string;
  description: string;
  status: FolderStatus;
  projectId: string;
  projectName: string;
  createdBy: string;
  createdAt: string;
  accessLevel: 'full' | 'view';
  entities?: FolderEntities;
  raw?: unknown;
}

export interface FolderEntities {
  tables?: Record<string, string>;
  files?: Record<string, string>;
  [key: string]: unknown;
}

// File types
export interface UploadedFile {
  id: string;
  name: string;
  size: number;
  type: string;
  status: 'pending' | 'uploaded' | 'error';
  uploadedAt: string;
  raw?: unknown;
}

// Session types
export interface Session {
  id: string;
  folderId: string;
  folderName: string;
  projectName: string;
  status: 'active' | 'inactive' | 'initializing';
  createdAt: string;
  appName?: string;
  selectedTableId?: string;
  selectedTableName?: string;
  transformRevision?: number;
  entities?: FolderEntities;
  raw?: unknown;
}

// Table types
export interface DataTable {
  id: string;
  name: string;
  source: 'uploaded' | 'agent_created';
  columns: string[];
  rows: Record<string, string | number>[];
  rowCount: number;
  isLoading?: boolean;
  hasMore?: boolean;
  page?: number;
  revision?: number;
  status?: 'ready' | 'inactive' | 'stale';
  recipe?: string[];
  sourceTables?: string[];
  createdAt?: string;
}

// Chat message types
export type MessageType = 'user' | 'agent' | 'activity' | 'tool_call' | 'tool_response' | 'error' | 'chart_result' | 'typing' | 'thinking' | 'transition';

/** Token accounting reported on the final response (from the completion event). */
export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface ChatMessage {
  id: string;
  type: MessageType;
  content: string;
  timestamp: string;
  metadata?: {
    toolName?: string;
    callId?: string;
    toolStatus?: 'pending' | 'complete' | 'error';
    toolArgs?: unknown;
    toolResponse?: unknown;
    chartType?: string;
    queryId?: string;
    /** Agent identity for thinking/transition rows. */
    agentName?: string;
    fromAgent?: string;
    toAgent?: string;
    agentLabel?: string;
    /** True while a thinking/answer message is still streaming in. */
    streaming?: boolean;
    /** Attached to the final agent message from the completion event. */
    tokenUsage?: TokenUsage;
    timeTaken?: number;
    durationMs?: number;
    success?: boolean;
    artifact?: ChartWidget;
    artifactStatus?: 'draft' | 'saving' | 'saved' | 'error';
  };
}

// Chart types
export type ChartType = 'line' | 'bar' | 'area' | 'pie' | 'radial' | 'kpi';

export interface ChartWidget {
  id: string;
  artifact_type?: 'chart';
  name: string;
  title?: string;
  type: ChartType;
  config: ChartConfig;
  data: ChartDataPoint[];
  position: { x: number; y: number; w: number; h: number };
  sourceTableId?: string;
  source_table_id?: string;
  xField?: string;
  yFields?: string[];
  transformRevision?: number;
  transform_revision?: number;
  status?: 'draft' | 'ready' | 'error';
  stale?: boolean;
  createdAt?: string;
  savedAt?: string;
}

export interface ChartConfig {
  primaryColor: string;
  showGrid: boolean;
  showLegend: boolean;
  showTooltip: boolean;
  lineType?: 'smooth' | 'straight';
  showDots?: boolean;
  barWidth?: number;
  stacking?: boolean;
  innerRadius?: number;
  gradientOpacity?: number;
}

export interface ChartDataPoint {
  label: string;
  value: number;
  category?: string;
}

// Report types
export type ReportFormat = 'PPTX' | 'PDF' | 'DOCX' | 'HTML';

export interface GeneratedReport {
  id: string;
  name: string;
  format: ReportFormat;
  status: 'generating' | 'ready' | 'error';
  createdAt: string;
  downloadUrl?: string;
  downloadUrls?: Partial<Record<ReportFormat, string>>;
  sourceTableId?: string;
  transformRevision?: number;
  body?: string;
  sections?: Array<{
    id: string;
    title: string;
    content: string;
    chart_ids?: string[];
    status?: string;
    included?: boolean;
  }>;
  stale?: boolean;
}

// Workspace view models
// The four workflow modes surfaced in the unified Workspace (Sources/Prepare/Visualize/Publish).
export type WorkspaceMode = 'sources' | 'prepare' | 'visualize' | 'publish';

// Derived pipeline stage for a folder (never stored - computed from folder tables).
// empty       : no tables in folder
// uploaded    : >=1 uploaded table, no agent-created table
// transformed : >=1 agent_created table
export type PipelineStage = 'empty' | 'uploaded' | 'transformed';

export interface PipelineState {
  stage: PipelineStage;
  hasUploadedTables: boolean;
  hasTransformTable: boolean;
  enabledModes: Record<WorkspaceMode, boolean>;
}

export interface ArtifactState {
  tables: DataTable[]; // Prepare
  charts: ChartWidget[]; // Visualize
  reports: GeneratedReport[]; // Publish
}

// License types
export interface License {
  key: string;
  type: string;
  status: 'active' | 'expired' | 'pending';
  issueDate: string;
  validTill: string;
  userLimits: {
    admin: { used: number; total: number };
    analyst: { used: number; total: number };
    viewer: { used: number; total: number };
  };
  resourceLimits: {
    totalProjects: number;
    activeProjects: number;
    transformations: number;
  };
}

// Access control types
export interface AccessGrant {
  userId: string;
  userName: string;
  projectId: string;
  projectName: string;
  permissionLevel: 'Project' | 'Partial' | 'Folder';
  folderIds?: string[];
  role: UserRole;
}

// Model types
export interface AIModel {
  id: string;
  name: string;
  provider: string;
  type: 'OpenRouter' | 'Google' | 'OpenAI' | 'Anthropic' | 'Meta' | 'Other';
  slug?: string;
}

export interface APIKeyEntry {
  provider: string;
  models: string[];
  hasKey: boolean;
}

// App state
export interface AppState {
  currentUser: User | null;
  selectedProject: Project | null;
  selectedFolder: Folder | null;
  activeSession: Session | null;
  isSidebarOpen: boolean;
  isServerOnline: boolean;
  notifications: Notification[];
}

export interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  title: string;
  message: string;
  timestamp: string;
  read: boolean;
}

// Lock state
export interface FolderLock {
  folderId: string;
  ownerId: string;
  ownerName: string;
  activity: string;
  expiresAt: string;
}

// Form state helpers
export interface FormField {
  value: string;
  error?: string;
  touched: boolean;
}

// Nav item
export interface NavItem {
  label: string;
  icon: string;
  route: string;
  roles: UserRole[];
  description?: string;
}

import type {
  User, Project, Folder, UploadedFile, Session, DataTable,
  ChartWidget, GeneratedReport, License, AccessGrant, AIModel,
  APIKeyEntry, FolderLock, ChatMessage
} from '@/types';

// Current user
export const currentUser: User = {
  id: 'u1',
  name: 'Alex Johnson',
  email: 'alex@company.com',
  role: 'Admin',
  status: 'active',
  createdAt: '2024-01-15',
};

// Users
export const users: User[] = [
  currentUser,
  { id: 'u2', name: 'Sarah Chen', email: 'sarah@company.com', role: 'Analyst', status: 'active', createdAt: '2024-02-01' },
  { id: 'u3', name: 'Mike Ross', email: 'mike@company.com', role: 'Viewer', status: 'active', createdAt: '2024-03-10' },
  { id: 'u4', name: 'Emily Davis', email: 'emily@company.com', role: 'Analyst', status: 'inactive', createdAt: '2024-04-05' },
  { id: 'u5', name: 'James Wilson', email: 'james@company.com', role: 'Viewer', status: 'active', createdAt: '2024-05-20' },
];

// Projects
export const projects: Project[] = [
  { id: 'p1', name: 'Sales Analytics', description: 'Comprehensive sales data analysis including quarterly performance, regional breakdowns, and trend forecasting. This project contains historical sales data from 2020-2025 across all regions.', status: 'Active', createdBy: 'Alex Johnson', createdAt: '2024-01-15', folderCount: 3 },
  { id: 'p2', name: 'Customer Insights', description: 'Customer behavior analysis, segmentation, and satisfaction tracking across all product lines and demographics.', status: 'Active', createdBy: 'Sarah Chen', createdAt: '2024-02-20', folderCount: 2 },
  { id: 'p3', name: 'Operations Review', description: 'Operational efficiency metrics, process optimization data, and resource utilization analysis.', status: 'Archived', createdBy: 'Alex Johnson', createdAt: '2024-03-01', folderCount: 1 },
  { id: 'p4', name: 'Marketing Performance', description: 'Campaign performance data, channel attribution, and ROI analysis for all marketing activities.', status: 'Active', createdBy: 'Mike Ross', createdAt: '2024-04-10', folderCount: 2 },
];

// Folders
export const folders: Folder[] = [
  { id: 'f1', name: 'Q1 2025 Sales', description: 'First quarter sales data including monthly breakdowns, regional performance, and product category analysis.', status: 'Active', projectId: 'p1', projectName: 'Sales Analytics', createdBy: 'Alex Johnson', createdAt: '2024-01-16', accessLevel: 'full' },
  { id: 'f2', name: 'Annual Comparison', description: 'Year-over-year comparison data from 2020-2025 with adjusted inflation metrics and growth rates.', status: 'Active', projectId: 'p1', projectName: 'Sales Analytics', createdBy: 'Sarah Chen', createdAt: '2024-01-20', accessLevel: 'full' },
  { id: 'f3', name: 'Regional Breakdown', description: 'Sales data broken down by North America, Europe, APAC, and LATAM regions with sub-regional detail.', status: 'Active', projectId: 'p1', projectName: 'Sales Analytics', createdBy: 'Alex Johnson', createdAt: '2024-02-01', accessLevel: 'view' },
  { id: 'f4', name: 'Customer Segments', description: 'RFM analysis, cohort data, and customer lifetime value calculations across all segments.', status: 'Active', projectId: 'p2', projectName: 'Customer Insights', createdBy: 'Sarah Chen', createdAt: '2024-02-21', accessLevel: 'full' },
  { id: 'f5', name: 'NPS Survey Results', description: 'Net Promoter Score survey data from Q4 2024 with verbatim responses and sentiment analysis.', status: 'Active', projectId: 'p2', projectName: 'Customer Insights', createdBy: 'Mike Ross', createdAt: '2024-03-05', accessLevel: 'view' },
  { id: 'f6', name: 'Legacy Data', description: 'Archived operational data from 2020-2023. Read-only reference material.', status: 'Archived', projectId: 'p3', projectName: 'Operations Review', createdBy: 'Alex Johnson', createdAt: '2024-03-02', accessLevel: 'full' },
  { id: 'f7', name: 'Campaign Q1', description: 'Q1 2025 marketing campaign data including email, social, and paid channel performance.', status: 'Active', projectId: 'p4', projectName: 'Marketing Performance', createdBy: 'Mike Ross', createdAt: '2024-04-11', accessLevel: 'full' },
  { id: 'f8', name: 'Attribution Model', description: 'Multi-touch attribution analysis with first-touch, last-touch, and linear comparison models.', status: 'Active', projectId: 'p4', projectName: 'Marketing Performance', createdBy: 'Emily Davis', createdAt: '2024-04-15', accessLevel: 'view' },
];

// Uploaded files
export const uploadedFiles: UploadedFile[] = [
  { id: 'file1', name: 'sales_q1_2025.csv', size: 2450000, type: 'csv', status: 'uploaded', uploadedAt: '2025-04-01' },
  { id: 'file2', name: 'customers_rfm.xlsx', size: 1820000, type: 'xlsx', status: 'uploaded', uploadedAt: '2025-04-02' },
  { id: 'file3', name: 'regional_data.csv', size: 890000, type: 'csv', status: 'uploaded', uploadedAt: '2025-04-03' },
];

// Sessions
export const sessions: Session[] = [
  { id: 'sess_1a2b3c4d', folderId: 'f1', folderName: 'Q1 2025 Sales', projectName: 'Sales Analytics', status: 'active', createdAt: '2025-04-01' },
  { id: 'sess_5e6f7g8h', folderId: 'f4', folderName: 'Customer Segments', projectName: 'Customer Insights', status: 'active', createdAt: '2025-04-02' },
];

// Data tables
export const dataTables: DataTable[] = [
  {
    id: 't1',
    name: 'Sales Data',
    source: 'uploaded',
    columns: ['Date', 'Region', 'Product', 'Revenue', 'Units', 'Channel'],
    rows: [
      { Date: '2025-01-01', Region: 'North America', Product: 'Widget Pro', Revenue: 45000, Units: 120, Channel: 'Direct' },
      { Date: '2025-01-01', Region: 'Europe', Product: 'Widget Lite', Revenue: 32000, Units: 200, Channel: 'Partner' },
      { Date: '2025-01-02', Region: 'APAC', Product: 'Widget Pro', Revenue: 28000, Units: 75, Channel: 'Online' },
      { Date: '2025-01-02', Region: 'North America', Product: 'Widget Max', Revenue: 67000, Units: 89, Channel: 'Direct' },
      { Date: '2025-01-03', Region: 'Europe', Product: 'Widget Pro', Revenue: 41000, Units: 110, Channel: 'Online' },
      { Date: '2025-01-03', Region: 'LATAM', Product: 'Widget Lite', Revenue: 19000, Units: 150, Channel: 'Partner' },
      { Date: '2025-01-04', Region: 'North America', Product: 'Widget Lite', Revenue: 23000, Units: 180, Channel: 'Online' },
      { Date: '2025-01-04', Region: 'APAC', Product: 'Widget Max', Revenue: 54000, Units: 72, Channel: 'Direct' },
    ],
    rowCount: 8,
  },
  {
    id: 't2',
    name: 'Customer Metrics',
    source: 'uploaded',
    columns: ['Customer ID', 'Segment', 'LTV', 'Last Purchase', 'NPS', 'Churn Risk'],
    rows: [
      { 'Customer ID': 'C1001', Segment: 'Enterprise', LTV: 125000, 'Last Purchase': '2025-03-15', NPS: 9, 'Churn Risk': 'Low' },
      { 'Customer ID': 'C1002', Segment: 'SMB', LTV: 45000, 'Last Purchase': '2025-02-28', NPS: 7, 'Churn Risk': 'Medium' },
      { 'Customer ID': 'C1003', Segment: 'Enterprise', LTV: 98000, 'Last Purchase': '2025-03-20', NPS: 10, 'Churn Risk': 'Low' },
      { 'Customer ID': 'C1004', Segment: 'Startup', LTV: 22000, 'Last Purchase': '2025-01-10', NPS: 5, 'Churn Risk': 'High' },
      { 'Customer ID': 'C1005', Segment: 'SMB', LTV: 38000, 'Last Purchase': '2025-03-25', NPS: 8, 'Churn Risk': 'Low' },
    ],
    rowCount: 5,
  },
  {
    id: 't3',
    name: 'Agent Summary',
    source: 'agent_created',
    columns: ['Metric', 'Q1 2025', 'Q4 2024', 'Change %', 'Trend'],
    rows: [
      { Metric: 'Total Revenue', 'Q1 2025': 305000, 'Q4 2024': 289000, 'Change %': 5.5, Trend: 'Up' },
      { Metric: 'Active Customers', 'Q1 2025': 1420, 'Q4 2024': 1380, 'Change %': 2.9, Trend: 'Up' },
      { Metric: 'Avg Order Value', 'Q1 2025': 2150, 'Q4 2024': 2095, 'Change %': 2.6, Trend: 'Up' },
      { Metric: 'Churn Rate', 'Q1 2025': 3.2, 'Q4 2024': 4.1, 'Change %': -22.0, Trend: 'Down' },
    ],
    rowCount: 4,
  },
];

// Chat messages (transform)
export const transformMessages: ChatMessage[] = [
  { id: 'm1', type: 'user', content: 'Analyze the revenue trends by region for Q1 2025', timestamp: '10:30 AM' },
  { id: 'm2', type: 'agent', content: 'I\'ve analyzed the revenue trends by region for Q1 2025. Here are the key findings:\n\n**North America** leads with $135K in revenue, followed by **Europe** at $73K, **APAC** at $82K, and **LATAM** at $19K.\n\nThe strongest growth channel is **Direct sales**, accounting for 55% of total revenue. Widget Pro is your top-performing product with $114K in sales.', timestamp: '10:31 AM' },
  { id: 'm3', type: 'activity', content: 'Analysis complete - 3 tools used', timestamp: '10:31 AM', metadata: { toolName: 'analyze_trends', toolStatus: 'complete' } },
  { id: 'm4', type: 'user', content: 'Create a chart showing revenue by product category', timestamp: '10:35 AM' },
  { id: 'm5', type: 'agent', content: 'Here\'s a chart breaking down revenue by product category:', timestamp: '10:36 AM' },
  { id: 'm6', type: 'chart_result', content: 'Revenue by Product - Bar Chart', timestamp: '10:36 AM', metadata: { chartType: 'bar' } },
];

// Dashboard messages
export const dashboardMessages: ChatMessage[] = [
  { id: 'd1', type: 'user', content: 'Show me the key metrics for this dashboard', timestamp: '11:00 AM' },
  { id: 'd2', type: 'agent', content: 'Here are the key metrics from your sales data:\n\n- **Total Revenue**: $305K (+5.5% vs Q4)\n- **Active Customers**: 1,420 (+2.9%)\n- **Avg Order Value**: $2,150 (+2.6%)\n- **Churn Rate**: 3.2% (-22% improvement)\n\nWould you like me to add any of these as charts to your dashboard?', timestamp: '11:01 AM' },
];

// Chart widgets
export const chartWidgets: ChartWidget[] = [
  {
    id: 'cw1',
    name: 'Revenue by Region',
    type: 'bar',
    config: { primaryColor: '#d08a5e', showGrid: true, showLegend: true, showTooltip: true, barWidth: 40 },
    data: [
      { label: 'North America', value: 135000 },
      { label: 'Europe', value: 73000 },
      { label: 'APAC', value: 82000 },
      { label: 'LATAM', value: 19000 },
    ],
    position: { x: 0, y: 0, w: 2, h: 2 },
  },
  {
    id: 'cw2',
    name: 'Revenue Trend',
    type: 'line',
    config: { primaryColor: '#22C55E', showGrid: true, showLegend: false, showTooltip: true, lineType: 'smooth', showDots: true },
    data: [
      { label: 'Jan 1', value: 77000 },
      { label: 'Jan 2', value: 95000 },
      { label: 'Jan 3', value: 60000 },
      { label: 'Jan 4', value: 73000 },
    ],
    position: { x: 2, y: 0, w: 2, h: 2 },
  },
  {
    id: 'cw3',
    name: 'Product Mix',
    type: 'pie',
    config: { primaryColor: '#A1A1AA', showGrid: false, showLegend: true, showTooltip: true, innerRadius: 40 },
    data: [
      { label: 'Widget Pro', value: 114000 },
      { label: 'Widget Lite', value: 74000 },
      { label: 'Widget Max', value: 121000 },
    ],
    position: { x: 0, y: 2, w: 2, h: 2 },
  },
];

// Generated reports
export const generatedReports: GeneratedReport[] = [
  { id: 'r1', name: 'Sales Q1 2025 Executive Summary', format: 'PDF', status: 'ready', createdAt: '2025-04-10' },
  { id: 'r2', name: 'Customer Analysis Presentation', format: 'PPTX', status: 'ready', createdAt: '2025-04-09' },
];

// License
export const license: License = {
  key: 'EVENTHORIZON-PRO-2025-ABCD1234',
  type: 'Professional',
  status: 'active',
  issueDate: '2025-01-01',
  validTill: '2026-01-01',
  userLimits: {
    admin: { used: 1, total: 5 },
    analyst: { used: 2, total: 10 },
    viewer: { used: 2, total: 25 },
  },
  resourceLimits: {
    totalProjects: 10,
    activeProjects: 6,
    transformations: 50,
  },
};

// Access grants
export const accessGrants: AccessGrant[] = [
  { userId: 'u2', userName: 'Sarah Chen', projectId: 'p1', projectName: 'Sales Analytics', permissionLevel: 'Project', role: 'Analyst' },
  { userId: 'u3', userName: 'Mike Ross', projectId: 'p1', projectName: 'Sales Analytics', permissionLevel: 'Folder', folderIds: ['f3'], role: 'Viewer' },
  { userId: 'u4', userName: 'Emily Davis', projectId: 'p2', projectName: 'Customer Insights', permissionLevel: 'Project', role: 'Analyst' },
];

// AI Models
export const aiModels: AIModel[] = [
  { id: 'm1', name: 'GPT-4o via OpenRouter', provider: 'OpenRouter', type: 'OpenRouter', slug: 'openai/gpt-4o' },
  { id: 'm2', name: 'Claude Sonnet via OpenRouter', provider: 'OpenRouter', type: 'OpenRouter', slug: 'anthropic/claude-sonnet-4.5' },
  { id: 'm3', name: 'Gemini Pro via OpenRouter', provider: 'OpenRouter', type: 'OpenRouter', slug: 'google/gemini-2.5-pro' },
  { id: 'm4', name: 'GPT-4o Direct', provider: 'OpenAI', type: 'OpenAI', slug: 'gpt-4o' },
  { id: 'm5', name: 'Gemini Direct', provider: 'Google', type: 'Google', slug: 'gemini/gemini-2.5-pro' },
];

// API Keys
export const apiKeys: APIKeyEntry[] = [
  { provider: 'OpenRouter', models: ['Any OpenRouter model slug', 'openai/gpt-4o', 'anthropic/claude-sonnet-4.5', 'google/gemini-2.5-pro'], hasKey: false },
  { provider: 'OpenAI', models: ['gpt-4o', 'gpt-4.1'], hasKey: false },
  { provider: 'Anthropic', models: ['claude-sonnet-4.5'], hasKey: false },
  { provider: 'Google', models: ['gemini-2.5-pro', 'gemini-2.5-flash'], hasKey: false },
];

// Folder lock example
export const folderLock: FolderLock = {
  folderId: 'f1',
  ownerId: 'u2',
  ownerName: 'Sarah Chen',
  activity: 'transforming data',
  expiresAt: '2025-04-15T12:00:00Z',
};

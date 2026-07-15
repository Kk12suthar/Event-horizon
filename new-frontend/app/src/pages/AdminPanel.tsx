import { useEffect, useState } from 'react';
import {
  Users, KeyRound, CreditCard, Cpu, FolderKanban,
  Plus, Pencil, Trash2, Search
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Progress } from '@/components/ui/progress';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { fetchAgentModelConfig, updateAgentModelConfig, type AgentModelConfig } from '@/lib/api';
import { users, license, apiKeys } from '@/data/mockData';
import type { User, UserRole } from '@/types';

type AdminTab = 'users' | 'access' | 'licenses' | 'model' | 'projects';

export function AdminPanel() {
  const [activeTab, setActiveTab] = useState<AdminTab>('users');

  const tabs = [
    { id: 'users' as AdminTab, label: 'Manage Users', icon: Users },
    { id: 'access' as AdminTab, label: 'Manage Access', icon: KeyRound },
    { id: 'licenses' as AdminTab, label: 'Manage Licenses', icon: CreditCard },
    { id: 'model' as AdminTab, label: 'Manage Model', icon: Cpu },
    { id: 'projects' as AdminTab, label: 'Manage Projects', icon: FolderKanban },
  ];

  return (
    <div className="flex flex-col md:flex-row h-full">
      <div className="w-full md:w-[200px] flex-shrink-0 bg-[#101010] border-b md:border-b-0 md:border-r border-[#242424]">
        <div className="p-4 border-b border-[#242424] hidden md:block">
          <h2 className="text-xs font-semibold text-white uppercase tracking-wider">Admin</h2>
        </div>
        <nav className="p-2 flex md:flex-col gap-1 overflow-x-auto md:space-y-1">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex-shrink-0 md:w-full flex items-center gap-2 md:gap-3 h-10 px-3 rounded-lg text-xs font-medium transition-all whitespace-nowrap ${
                activeTab === tab.id
                  ? 'text-white bg-[#181818] border md:border-0 md:border-l-2 border-[#c16e43]'
                  : 'text-[#A1A1AA] hover:bg-[#1C1C1C] hover:text-white'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      <div className="flex-1 overflow-y-auto p-4 md:p-6">
        <h1 className="text-lg md:text-xl font-bold text-white mb-4 md:mb-6">Admin / {tabs.find(t => t.id === activeTab)?.label}</h1>
        {activeTab === 'users' && <UsersTab />}
        {activeTab === 'access' && <AccessTab />}
        {activeTab === 'licenses' && <LicensesTab />}
        {activeTab === 'model' && <ModelTab />}
        {activeTab === 'projects' && <ProjectsTab />}
      </div>
    </div>
  );
}

function UsersTab() {
  const [showInvite, setShowInvite] = useState(false);
  const [showEdit, setShowEdit] = useState<User | null>(null);
  const [showDelete, setShowDelete] = useState<User | null>(null);
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState<UserRole>('Viewer');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [editRole, setEditRole] = useState<UserRole>('Viewer');

  const handleInvite = () => {
    if (!inviteEmail.trim()) return;
    setIsSubmitting(true);
    setTimeout(() => {
      setIsSubmitting(false);
      setShowInvite(false);
      setInviteEmail('');
    }, 800);
  };

  const handleEdit = () => {
    if (!showEdit) return;
    setIsSubmitting(true);
    setTimeout(() => {
      setIsSubmitting(false);
      setShowEdit(null);
    }, 800);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="relative w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
          <Input placeholder="Search users..." className="pl-9 h-9 bg-[#101010] border-[#242424] text-white placeholder:text-[#71717A]" />
        </div>
        <Button onClick={() => setShowInvite(true)} className="h-9 bg-[#c16e43] text-[#0A0A0A] hover:bg-[#d08a5e]">
          <Plus className="w-4 h-4 mr-1" />
          Invite User
        </Button>
      </div>

      <div className="bg-[#101010] border border-[#242424] rounded-xl overflow-x-auto">
        <table className="w-full min-w-[640px]">
          <thead>
            <tr className="border-b border-[#242424]">
              <th className="text-left px-4 py-3 text-xs font-medium text-[#A1A1AA] uppercase tracking-wider">User</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-[#A1A1AA] uppercase tracking-wider">Role</th>
              <th className="text-left px-4 py-3 text-xs font-medium text-[#A1A1AA] uppercase tracking-wider">Status</th>
              <th className="text-right px-4 py-3 text-xs font-medium text-[#A1A1AA] uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map(user => (
              <tr key={user.id} className="border-b border-[#242424] last:border-0 hover:bg-[#1C1C1C] transition-colors">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-[#c16e43] flex items-center justify-center text-white text-xs font-semibold">
                      {user.name.split(' ').map(n => n[0]).join('')}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-white">{user.name}</p>
                      <p className="text-xs text-[#71717A]">{user.email}</p>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    user.role === 'Admin' ? 'bg-[#c16e43]/10 text-[#E4E4E7]' :
                    user.role === 'Analyst' ? 'bg-[#A1A1AA]/10 text-[#A1A1AA]' :
                    'bg-[#71717A]/10 text-[#71717A]'
                  }`}>
                    {user.role}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    user.status === 'active' ? 'bg-[#22C55E]/10 text-[#22C55E]' :
                    'bg-[#F97066]/10 text-[#F97066]'
                  }`}>
                    {user.status}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1">
                    <button onClick={() => { setShowEdit(user); setEditRole(user.role); }} className="p-1.5 rounded-lg text-[#71717A] hover:text-white hover:bg-[#1C1C1C]">
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                    <button onClick={() => setShowDelete(user)} className="p-1.5 rounded-lg text-[#71717A] hover:text-[#F97066] hover:bg-[#F97066]/10">
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Dialog open={showInvite} onOpenChange={setShowInvite}>
        <DialogContent className="bg-[#101010] border-[#242424] max-w-md">
          <DialogHeader><DialogTitle className="text-lg font-semibold text-white">Invite New User</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div>
              <label className="text-xs text-[#A1A1AA] uppercase">Email Address</label>
              <Input value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} placeholder="user@company.com" className="mt-1 bg-[#000000] border-[#242424] text-white" />
            </div>
            <div>
              <label className="text-xs text-[#A1A1AA] uppercase">Role</label>
              <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value as UserRole)} className="mt-1 w-full h-10 bg-[#000000] border border-[#242424] rounded-lg px-3 text-white text-sm">
                <option value="Viewer">Viewer - Read only access</option>
                <option value="Analyst">Analyst - Can modify data</option>
                <option value="Admin">Admin - Full system access</option>
              </select>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => setShowInvite(false)} className="border-[#242424] text-[#A1A1AA] hover:bg-[#1C1C1C]">Cancel</Button>
              <Button onClick={handleInvite} disabled={!inviteEmail.trim() || isSubmitting} className="bg-[#c16e43] text-[#0A0A0A] hover:bg-[#d08a5e]">
                {isSubmitting ? 'Sending...' : 'Send Invitation'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={!!showEdit} onOpenChange={() => setShowEdit(null)}>
        <DialogContent className="bg-[#101010] border-[#242424] max-w-md">
          <DialogHeader><DialogTitle className="text-lg font-semibold text-white">Edit User</DialogTitle></DialogHeader>
          <div className="space-y-4 mt-2">
            <div>
              <label className="text-xs text-[#A1A1AA] uppercase">Full Name</label>
              <Input value={showEdit?.name || ''} disabled className="mt-1 bg-[#000000] border-[#242424] text-[#71717A] opacity-50" />
            </div>
            <div>
              <label className="text-xs text-[#A1A1AA] uppercase">Role</label>
              <select value={editRole} onChange={(e) => setEditRole(e.target.value as UserRole)} className="mt-1 w-full h-10 bg-[#000000] border border-[#242424] rounded-lg px-3 text-white text-sm">
                <option value="Viewer">Viewer</option>
                <option value="Analyst">Analyst</option>
                <option value="Admin">Admin</option>
              </select>
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => setShowEdit(null)} className="border-[#242424] text-[#A1A1AA] hover:bg-[#1C1C1C]">Cancel</Button>
              <Button onClick={handleEdit} disabled={isSubmitting} className="bg-[#c16e43] text-[#0A0A0A] hover:bg-[#d08a5e]">
                {isSubmitting ? 'Updating...' : 'Save Changes'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <ConfirmDialog open={!!showDelete} onOpenChange={() => setShowDelete(null)} title="Delete User?" description={`This will remove ${showDelete?.name} from the workspace. This action cannot be undone.`} onConfirm={() => setShowDelete(null)} />
    </div>
  );
}

function AccessTab() {
  const [activeSubTab, setActiveSubTab] = useState<'list' | 'grant' | 'edit' | 'revoke'>('list');

  const subTabs = [
    { id: 'list' as const, label: 'Access List' },
    { id: 'grant' as const, label: 'Grant Access' },
    { id: 'edit' as const, label: 'Edit Access' },
    { id: 'revoke' as const, label: 'Revoke Access' },
  ];

  return (
    <div>
      <div className="flex gap-1 mb-6 bg-[#101010] border border-[#242424] rounded-lg p-1 w-fit">
        {subTabs.map(tab => (
          <button key={tab.id} onClick={() => setActiveSubTab(tab.id)} className={`px-4 py-2 rounded-md text-xs font-medium transition-colors ${activeSubTab === tab.id ? 'bg-[#c16e43] text-[#0A0A0A]' : 'text-[#A1A1AA] hover:text-white'}`}>
            {tab.label}
          </button>
        ))}
      </div>

      {activeSubTab === 'list' && (
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-white">Users with Access</h3>
          {users.slice(0, 3).map(user => (
            <div key={user.id} className="bg-[#101010] border border-[#242424] rounded-xl p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-[#c16e43] flex items-center justify-center text-white text-xs font-semibold">
                    {user.name.split(' ').map(n => n[0]).join('')}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-white">{user.name}</p>
                    <p className="text-xs text-[#71717A]">{user.email}</p>
                  </div>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                  user.role === 'Admin' ? 'bg-[#c16e43]/10 text-[#E4E4E7]' :
                  user.role === 'Analyst' ? 'bg-[#A1A1AA]/10 text-[#A1A1AA]' :
                  'bg-[#71717A]/10 text-[#71717A]'
                }`}>{user.role}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {activeSubTab === 'grant' && (
        <div className="max-w-lg bg-[#101010] border border-[#242424] rounded-xl p-6 space-y-4">
          <div>
            <label className="text-xs text-[#A1A1AA] uppercase">Select User</label>
            <select className="mt-1 w-full h-10 bg-[#000000] border border-[#242424] rounded-lg px-3 text-white text-sm"><option>Choose a user...</option>{users.map(u => <option key={u.id} value={u.id}>{u.name} ({u.email})</option>)}</select>
          </div>
          <div>
            <label className="text-xs text-[#A1A1AA] uppercase">Select Project</label>
            <select className="mt-1 w-full h-10 bg-[#000000] border border-[#242424] rounded-lg px-3 text-white text-sm"><option>Choose a project...</option></select>
          </div>
          <div>
            <label className="text-xs text-[#A1A1AA] uppercase">Permission Level</label>
            <select className="mt-1 w-full h-10 bg-[#000000] border border-[#242424] rounded-lg px-3 text-white text-sm"><option>Project</option><option>Partial</option><option>Folder</option></select>
          </div>
          <div>
            <label className="text-xs text-[#A1A1AA] uppercase">Role</label>
            <select className="mt-1 w-full h-10 bg-[#000000] border border-[#242424] rounded-lg px-3 text-white text-sm"><option value="Viewer">Viewer</option><option value="Analyst">Analyst</option></select>
          </div>
          <Button className="w-full bg-[#c16e43] text-[#0A0A0A] hover:bg-[#d08a5e]">Grant Access</Button>
        </div>
      )}

      {activeSubTab === 'edit' && (
        <div className="text-center py-12"><p className="text-sm text-[#71717A]">Select a user and project to edit their access.</p></div>
      )}

      {activeSubTab === 'revoke' && (
        <div className="max-w-lg bg-[#101010] border border-[#242424] rounded-xl p-6 space-y-4">
          <div className="p-4 bg-[#F97066]/10 border border-[#F97066]/20 rounded-lg"><p className="text-sm text-[#F97066]">Warning: Revoking access will immediately remove the user&apos;s ability to view or interact with the selected project.</p></div>
          <div>
            <label className="text-xs text-[#A1A1AA] uppercase">Select Project</label>
            <select className="mt-1 w-full h-10 bg-[#000000] border border-[#242424] rounded-lg px-3 text-white text-sm"><option>Choose a project...</option></select>
          </div>
          <div>
            <label className="text-xs text-[#A1A1AA] uppercase">Select User</label>
            <select className="mt-1 w-full h-10 bg-[#000000] border border-[#242424] rounded-lg px-3 text-white text-sm"><option>Choose a user...</option></select>
          </div>
          <Button className="w-full bg-[#F97066] text-white hover:bg-[#E85C50]">Revoke Access</Button>
        </div>
      )}
    </div>
  );
}

function LicensesTab() {
  const [activeSubTab, setActiveSubTab] = useState<'view' | 'manage'>('view');

  return (
    <div>
      <div className="flex gap-1 mb-6 bg-[#101010] border border-[#242424] rounded-lg p-1 w-fit">
        <button onClick={() => setActiveSubTab('view')} className={`px-4 py-2 rounded-md text-xs font-medium ${activeSubTab === 'view' ? 'bg-[#c16e43] text-[#0A0A0A]' : 'text-[#A1A1AA]'}`}>View License Info</button>
        <button onClick={() => setActiveSubTab('manage')} className={`px-4 py-2 rounded-md text-xs font-medium ${activeSubTab === 'manage' ? 'bg-[#c16e43] text-[#0A0A0A]' : 'text-[#A1A1AA]'}`}>Manage License</button>
      </div>

      {activeSubTab === 'view' ? (
        <div className="space-y-6">
          <div className="bg-[#101010] border border-[#242424] rounded-xl p-6">
            <h3 className="text-sm font-semibold text-white mb-4">License Key</h3>
            <code className="block bg-[#000000] border border-[#242424] rounded-lg px-4 py-3 text-sm font-mono text-[#E4E4E7]">{license.key}</code>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-4">
              <div><p className="text-xs text-[#71717A]">License Type</p><p className="text-sm font-medium text-white">{license.type}</p></div>
              <div><p className="text-xs text-[#71717A]">Status</p><span className="text-xs px-2 py-0.5 bg-[#22C55E]/10 text-[#22C55E] rounded-full font-medium">{license.status}</span></div>
              <div><p className="text-xs text-[#71717A]">Issue Date</p><p className="text-sm font-medium text-white">{license.issueDate}</p></div>
              <div><p className="text-xs text-[#71717A]">Valid Till</p><p className="text-sm font-medium text-white">{license.validTill}</p></div>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-white mb-4">User Limits</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {Object.entries(license.userLimits).map(([role, limits]) => (
                <div key={role} className="bg-[#101010] border border-[#242424] rounded-xl p-4">
                  <p className="text-xs text-[#A1A1AA] capitalize">{role}s</p>
                  <p className="text-lg font-bold text-white mt-1">{limits.used} / {limits.total}</p>
                  <Progress value={(limits.used / limits.total) * 100} className="h-1.5 mt-2 bg-[#242424]" />
                </div>
              ))}
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-white mb-4">Resource Limits</h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-[#101010] border border-[#242424] rounded-xl p-4"><p className="text-xs text-[#A1A1AA]">Total Projects</p><p className="text-lg font-bold text-white">{license.resourceLimits.totalProjects}</p></div>
              <div className="bg-[#101010] border border-[#242424] rounded-xl p-4"><p className="text-xs text-[#A1A1AA]">Active Projects</p><p className="text-lg font-bold text-white">{license.resourceLimits.activeProjects}</p></div>
              <div className="bg-[#101010] border border-[#242424] rounded-xl p-4"><p className="text-xs text-[#A1A1AA]">Transformations</p><p className="text-lg font-bold text-white">{license.resourceLimits.transformations}</p></div>
            </div>
          </div>
        </div>
      ) : (
        <div className="max-w-lg bg-[#101010] border border-[#242424] rounded-xl p-6 space-y-6">
          <div>
            <label className="text-xs text-[#A1A1AA] uppercase">New License Key</label>
            <Input placeholder="Enter license key" className="mt-1 bg-[#000000] border-[#242424] text-white" />
            <p className="text-xs text-[#F59E0B] mt-2">Warning: Updating the license may require a restart.</p>
            <Button className="mt-3 bg-[#c16e43] text-[#0A0A0A] hover:bg-[#d08a5e]">Update License</Button>
          </div>
          <div className="border-t border-[#242424] pt-6">
            <label className="text-xs text-[#A1A1AA] uppercase">Upload License File</label>
            <Input type="file" accept=".lic,.key" className="mt-1 bg-[#000000] border-[#242424] text-white" />
            <Button className="mt-3 bg-[#c16e43] text-[#0A0A0A] hover:bg-[#d08a5e]">Upload License</Button>
          </div>
        </div>
      )}
    </div>
  );
}

function ModelTab() {
  const [activeSubTab, setActiveSubTab] = useState<'runtime' | 'keys' | 'config'>('runtime');
  const [provider, setProvider] = useState('openrouter');
  const [model, setModel] = useState('openai/gpt-4o');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('https://openrouter.ai/api/v1');
  const [siteUrl, setSiteUrl] = useState('http://localhost:5174');
  const [appName, setAppName] = useState('EventHorizon');
  const [temperature, setTemperature] = useState(0.2);
  const [runtimeConfig, setRuntimeConfig] = useState<AgentModelConfig | null>(null);
  const [statusMessage, setStatusMessage] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  const providers = [
    { id: 'openrouter', label: 'OpenRouter', keyEnv: 'OPENROUTER_API_KEY', helper: 'Recommended: one API key can route to any OpenRouter model slug.' },
    { id: 'openai', label: 'OpenAI Direct', keyEnv: 'OPENAI_API_KEY', helper: 'Use for direct OpenAI model calls.' },
    { id: 'anthropic', label: 'Anthropic Direct', keyEnv: 'ANTHROPIC_API_KEY', helper: 'Use for direct Claude model calls.' },
    { id: 'google', label: 'Google Gemini Direct', keyEnv: 'GOOGLE_API_KEY', helper: 'Use for direct Gemini (AI Studio) model calls.' },
    { id: 'vertex', label: 'Google Vertex AI', keyEnv: 'VERTEX_API_KEY', helper: 'Vertex AI. Leave key blank to use gcloud ADC, or paste a Vertex Express (AQ...) key.' },
  ];

  const openRouterExamples = ['openai/gpt-4o', '~openai/gpt-latest', 'anthropic/claude-sonnet-4.5', 'google/gemini-2.5-pro', 'meta-llama/llama-3.3-70b-instruct'];
  const directExamples: Record<string, string[]> = {
    openai: ['gpt-4o', 'gpt-4.1', 'o3-mini'],
    anthropic: ['anthropic/claude-sonnet-4.5', 'anthropic/claude-haiku-4.5'],
    google: ['gemini-3.5-flash', 'gemini/gemini-2.5-pro', 'gemini/gemini-2.5-flash'],
    vertex: ['gemini-3.5-flash', 'gemini-2.5-pro', 'gemini-2.5-flash'],
  };
  const examples = provider === 'openrouter' ? openRouterExamples : directExamples[provider] || [];
  const selectedProvider = providers.find(item => item.id === provider) || providers[0];
  const resolvedPreview = provider === 'openrouter' && model && !model.startsWith('openrouter/') ? `openrouter/${model}` : model;
  const activeRuntimeModel = runtimeConfig?.resolved_model || resolvedPreview || 'Not configured';
  const activeRuntimeProvider = runtimeConfig?.provider || provider;

  useEffect(() => {
    let mounted = true;
    fetchAgentModelConfig()
      .then((config) => {
        if (!mounted) return;
        setRuntimeConfig(config);
        setProvider(config.provider || 'openrouter');
        const displayModel = config.provider === 'openrouter' && config.resolved_model?.startsWith('openrouter/')
          ? config.resolved_model.replace(/^openrouter\//, '')
          : config.model || config.resolved_model || 'openai/gpt-4o';
        if (displayModel) setModel(displayModel);
        if (config.base_url) setBaseUrl(config.base_url);
        if (config.site_url) setSiteUrl(config.site_url);
        if (config.app_name) setAppName(config.app_name);
        if (typeof config.temperature === 'number') setTemperature(config.temperature);
      })
      .catch((error) => setStatusMessage(error instanceof Error ? error.message : 'Could not load model configuration.'))
      .finally(() => {
        if (mounted) setIsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    setStatusMessage('');
    try {
      const updated = await updateAgentModelConfig({
        provider,
        model,
        api_key: apiKey.trim() || undefined,
        base_url: provider === 'openrouter' ? baseUrl : undefined,
        site_url: provider === 'openrouter' ? siteUrl : undefined,
        app_name: provider === 'openrouter' ? appName : undefined,
        temperature,
      });
      setRuntimeConfig(updated);
      setApiKey('');
      setStatusMessage('Runtime model configuration updated. New chat requests will use this provider and model.');
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : 'Failed to update model configuration.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-[#262626] bg-[#0D0D0D] p-5">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-[#8C8C8C]">AI Runtime</p>
          <h2 className="mt-1 text-xl font-semibold text-white">Model and API key setup</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-[#B8B8B8]">
            OpenRouter is the recommended path: enter any OpenRouter model slug and one OpenRouter key. The server calls LiteLLM with the required <span className="font-mono text-[#E9B872]">openrouter/</span> prefix automatically.
          </p>
        </div>
        <div className={`rounded-full px-3 py-1 text-xs font-semibold ${runtimeConfig?.key_configured ? 'bg-[#22C55E]/10 text-[#22C55E]' : 'bg-[#E9B872]/10 text-[#E9B872]'}`}>
          {runtimeConfig?.key_configured ? 'Key configured' : 'Key needed'}
        </div>
      </div>

      <div className="flex gap-1 rounded-xl border border-[#262626] bg-[#0D0D0D] p-1 w-fit">
        <button onClick={() => setActiveSubTab('runtime')} className={`px-4 py-2 rounded-lg text-xs font-medium ${activeSubTab === 'runtime' ? 'bg-[#c16e43] text-[#0A0A0A]' : 'text-[#A1A1AA] hover:text-white'}`}>Runtime Setup</button>
        <button onClick={() => setActiveSubTab('keys')} className={`px-4 py-2 rounded-lg text-xs font-medium ${activeSubTab === 'keys' ? 'bg-[#c16e43] text-[#0A0A0A]' : 'text-[#A1A1AA] hover:text-white'}`}>Provider Keys</button>
        <button onClick={() => setActiveSubTab('config')} className={`px-4 py-2 rounded-lg text-xs font-medium ${activeSubTab === 'config' ? 'bg-[#c16e43] text-[#0A0A0A]' : 'text-[#A1A1AA] hover:text-white'}`}>Agent Assignment</button>
      </div>

      {activeSubTab === 'runtime' && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="rounded-2xl border border-[#262626] bg-[#0D0D0D] p-6">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="text-xs uppercase tracking-wider text-[#8C8C8C]">Provider</label>
                <select value={provider} onChange={(event) => setProvider(event.target.value)} className="mt-1 h-10 w-full rounded-xl border border-[#262626] bg-[#000000] px-3 text-sm text-white outline-none">
                  {providers.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
                <p className="mt-2 text-xs leading-5 text-[#8C8C8C]">{selectedProvider.helper}</p>
              </div>
              <div>
                <label className="text-xs uppercase tracking-wider text-[#8C8C8C]">Model slug</label>
                <Input value={model} onChange={(event) => setModel(event.target.value)} placeholder="openai/gpt-4o" className="mt-1 bg-[#000000] border-[#262626] text-white" />
                <p className="mt-2 text-xs leading-5 text-[#8C8C8C]">Runtime value: <span className="font-mono text-[#E9B872]">{resolvedPreview || 'not set'}</span></p>
              </div>
              <div>
                <label className="text-xs uppercase tracking-wider text-[#8C8C8C]">{selectedProvider.keyEnv}</label>
                <Input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={runtimeConfig?.key_configured ? 'Leave blank to keep current key' : 'Paste API key'} className="mt-1 bg-[#000000] border-[#262626] text-white" />
              </div>
              <div>
                <label className="text-xs uppercase tracking-wider text-[#8C8C8C]">Temperature</label>
                <Input type="number" min="0" max="2" step="0.1" value={temperature} onChange={(event) => setTemperature(Number(event.target.value))} className="mt-1 bg-[#000000] border-[#262626] text-white" />
              </div>
              {provider === 'openrouter' && (
                <>
                  <div>
                    <label className="text-xs uppercase tracking-wider text-[#8C8C8C]">OpenRouter base URL</label>
                    <Input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} className="mt-1 bg-[#000000] border-[#262626] text-white" />
                  </div>
                  <div>
                    <label className="text-xs uppercase tracking-wider text-[#8C8C8C]">App title</label>
                    <Input value={appName} onChange={(event) => setAppName(event.target.value)} className="mt-1 bg-[#000000] border-[#262626] text-white" />
                  </div>
                  <div className="md:col-span-2">
                    <label className="text-xs uppercase tracking-wider text-[#8C8C8C]">HTTP referer / site URL</label>
                    <Input value={siteUrl} onChange={(event) => setSiteUrl(event.target.value)} className="mt-1 bg-[#000000] border-[#262626] text-white" />
                  </div>
                </>
              )}
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              {examples.map(example => (
                <button key={example} onClick={() => setModel(example)} className="rounded-full border border-[#262626] bg-[#000000] px-3 py-1.5 text-xs text-[#B8B8B8] transition-colors hover:border-[#c16e43] hover:text-white">
                  {example}
                </button>
              ))}
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Button onClick={handleSave} disabled={isSaving || isLoading || !model.trim()} className="bg-[#c16e43] text-[#0A0A0A] hover:bg-[#d08a5e] disabled:opacity-50">
                {isSaving ? 'Saving...' : 'Save Runtime Config'}
              </Button>
              {statusMessage && <p className="text-sm text-[#B8B8B8]">{statusMessage}</p>}
            </div>
          </div>

          <div className="rounded-2xl border border-[#262626] bg-[#0D0D0D] p-6">
            <h3 className="text-sm font-semibold text-white">Current runtime</h3>
            <div className="mt-4 space-y-3 text-sm">
              <RuntimeRow label="Provider" value={runtimeConfig?.provider || provider} />
              <RuntimeRow label="Model" value={runtimeConfig?.resolved_model || resolvedPreview || 'Not configured'} mono />
              <RuntimeRow label="Key env" value={runtimeConfig?.key_env || selectedProvider.keyEnv} mono />
              <RuntimeRow label="Key status" value={runtimeConfig?.key_configured ? 'Configured' : 'Missing'} />
              <RuntimeRow label="Base URL" value={runtimeConfig?.base_url || baseUrl || 'Default'} mono />
            </div>
            <div className="mt-5 rounded-xl border border-[#E9B872]/20 bg-[#E9B872]/10 p-4 text-xs leading-5 text-[#E9D4AA]">
              For OpenRouter, the UI accepts slugs like <span className="font-mono">openai/gpt-4o</span>. The agent sends <span className="font-mono">openrouter/openai/gpt-4o</span> to LiteLLM.
            </div>
          </div>
        </div>
      )}

      {activeSubTab === 'keys' && (
        <div className="rounded-2xl border border-[#262626] bg-[#0D0D0D] overflow-x-auto">
          <table className="w-full min-w-[560px]">
            <thead><tr className="border-b border-[#262626]"><th className="text-left px-4 py-3 text-xs font-medium text-[#8C8C8C] uppercase">Provider</th><th className="text-left px-4 py-3 text-xs font-medium text-[#8C8C8C] uppercase">Models</th><th className="text-left px-4 py-3 text-xs font-medium text-[#8C8C8C] uppercase">Runtime Key Status</th></tr></thead>
            <tbody>{apiKeys.map((key) => {
              const isRuntimeProvider = key.provider.toLowerCase().replace(/\s+/g, '') === provider.replace(/_/g, '');
              const configured = isRuntimeProvider ? Boolean(runtimeConfig?.key_configured) : key.hasKey;
              return (
                <tr key={key.provider} className="border-b border-[#262626] last:border-0 hover:bg-[#1B1B1B]">
                  <td className="px-4 py-3 text-sm text-white">{key.provider}</td>
                  <td className="px-4 py-3 text-sm text-[#B8B8B8]">{key.models.join(', ')}</td>
                  <td className="px-4 py-3"><span className={`text-xs px-2 py-0.5 rounded-full font-medium ${configured ? 'bg-[#22C55E]/10 text-[#22C55E]' : 'bg-[#F97066]/10 text-[#F97066]'}`}>{configured ? 'Configured' : 'Missing'}</span></td>
                </tr>
              );
            })}</tbody>
          </table>
        </div>
      )}

      {activeSubTab === 'config' && (
        <div className="space-y-6">
          <div className="rounded-2xl border border-[#262626] bg-[#0D0D0D] p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-[#8C8C8C]">Runtime assignment</p>
                <h3 className="mt-1 text-lg font-semibold text-white">All agent surfaces use the active runtime model</h3>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-[#B8B8B8]">
                  There is no separate tools model. The LangGraph nodes call deterministic backend tools, then the configured runtime model writes the final answer using that tool evidence.
                </p>
              </div>
              <span className={`rounded-full px-3 py-1 text-xs font-semibold ${runtimeConfig?.key_configured ? 'bg-[#22C55E]/10 text-[#22C55E]' : 'bg-[#E9B872]/10 text-[#E9B872]'}`}>
                {runtimeConfig?.key_configured ? 'Ready for chat' : 'API key required'}
              </span>
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-3">
              {[
                { name: 'Transformation Chat', description: 'Uses folder tables, selected table context, and safe SQL tools for transform/data questions.' },
                { name: 'Dashboard Assistant', description: 'Uses the same model for dashboard analysis after backend tool evidence is collected.' },
                { name: 'Report Assistant', description: 'Uses the same model to draft report content from current session and folder context.' },
              ].map(agent => (
                <div key={agent.name} className="rounded-xl border border-[#262626] bg-[#000000] p-4">
                  <h4 className="text-sm font-semibold text-white">{agent.name}</h4>
                  <p className="mt-2 min-h-[44px] text-xs leading-5 text-[#8C8C8C]">{agent.description}</p>
                  <div className="mt-4 space-y-3">
                    <RuntimeRow label="Provider" value={activeRuntimeProvider} />
                    <RuntimeRow label="Answer model" value={activeRuntimeModel} mono />
                    <RuntimeRow label="Tool execution" value="Backend tools, no separate model" />
                  </div>
                </div>
              ))}
            </div>

            <div className="mt-5 rounded-xl border border-[#262626] bg-[#101010] p-4 text-xs leading-5 text-[#D8D8D8]">
              Change provider, model slug, or API key in Runtime Setup. New chat, dashboard, and report requests use that runtime immediately.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function RuntimeRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wider text-[#8C8C8C]">{label}</p>
      <p className={`mt-1 break-words text-white ${mono ? 'font-mono text-xs' : 'text-sm'}`}>{value}</p>
    </div>
  );
}
function ProjectsTab() {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('All');

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <div className="relative w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
          <Input placeholder="Search projects..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="pl-9 h-9 bg-[#101010] border-[#242424] text-white placeholder:text-[#71717A]" />
        </div>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="h-9 bg-[#101010] border border-[#242424] rounded-lg px-3 text-white text-sm">
          <option>All Status</option><option>Active</option><option>Archived</option><option>Deleted</option>
        </select>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {['Sales Analytics', 'Customer Insights', 'Operations Review', 'Marketing Performance'].map((name, i) => (
          <div key={i} className="bg-[#101010] border border-[#242424] rounded-xl p-5 hover:border-[#383838] transition-colors">
            <div className="flex items-start justify-between">
              <div><h3 className="text-sm font-semibold text-white">{name}</h3><p className="text-xs text-[#71717A] mt-1">Project description goes here...</p></div>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${i < 3 ? 'bg-[#22C55E]/10 text-[#22C55E]' : 'bg-[#71717A]/10 text-[#71717A]'}`}>{i < 3 ? 'Active' : 'Archived'}</span>
            </div>
            <div className="flex items-center gap-4 mt-4 text-xs text-[#71717A]"><span>Created by Admin</span><span>2024-0{i + 1}-15</span></div>
          </div>
        ))}
      </div>
    </div>
  );
}

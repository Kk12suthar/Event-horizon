import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type {
  ChartWidget,
  DataTable,
  Folder,
  FolderEntities,
  GeneratedReport,
  Project,
  Session,
  UploadedFile,
} from '@/types';
import {
  createFolderRecord,
  createProjectRecord,
  createSessionRecord,
  deleteFolderRecord,
  deleteProjectRecord,
  fetchAllFolderTables,
  fetchFolderById,
  fetchProjectsForUser,
  fetchSessionByFolderAndUser,
  fetchTablePreview,
  normalizeFolderStatus,
  normalizeProjectStatus,
  updateFolderRecord,
  updateProjectRecord,
  unwrapData,
} from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

interface AppStateContextValue {
  selectedProject: Project | null;
  selectedFolder: Folder | null;
  activeSession: Session | null;
  isSidebarOpen: boolean;
  isServerOnline: boolean;
  projectList: Project[];
  folderList: Folder[];
  fileList: UploadedFile[];
  sessionList: Session[];
  tables: DataTable[];
  charts: ChartWidget[];
  reports: GeneratedReport[];
  isLoading: boolean;
  errorMessage: string | null;
  setIsLoading: (value: boolean) => void;
  setIsServerOnline: (value: boolean) => void;
  setActiveSession: (session: Session | null) => void;
  selectProject: (project: Project | null) => void;
  selectFolder: (folder: Folder | null) => void;
  loadFolderContext: (folderId: string) => Promise<Folder | null>;
  refreshProjects: () => Promise<void>;
  ensureSession: () => Promise<Session | null>;
  loadTablesForFolder: (folder: Folder) => Promise<DataTable[]>;
  loadTablePreview: (tableId: string, page?: number, limit?: number) => Promise<DataTable | null>;
  toggleSidebar: () => void;
  createProject: (name: string, description: string, status: Project['status']) => Promise<Project | null>;
  updateProject: (id: string, updates: Partial<Project>) => Promise<void>;
  deleteProject: (id: string) => Promise<void>;
  createFolder: (name: string, description: string, projectId: string) => Promise<Folder | null>;
  updateFolder: (id: string, updates: Partial<Folder>) => Promise<void>;
  deleteFolder: (id: string) => Promise<void>;
  addFiles: (newFiles: UploadedFile[]) => void;
  removeFile: (id: string) => void;
  addChart: (chart: ChartWidget) => void;
  removeChart: (id: string) => void;
  addReport: (report: GeneratedReport) => void;
  getProjectFolders: (projectId: string) => Folder[];
}

const AppStateContext = createContext<AppStateContextValue | null>(null);

const toRecord = (value: unknown): Record<string, unknown> => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
};

const parseMaybeJson = (value: unknown): unknown => {
  if (typeof value !== 'string') return value;
  try {
    return JSON.parse(value) as unknown;
  } catch {
    return value;
  }
};

const parseEntities = (value: unknown): FolderEntities => {
  const parsed = parseMaybeJson(value);
  const record = toRecord(parsed);
  return {
    ...record,
    tables: toStringMap(record.tables),
    files: toStringMap(record.files),
  };
};

const toStringMap = (value: unknown): Record<string, string> => {
  const record = toRecord(parseMaybeJson(value));
  return Object.fromEntries(Object.entries(record).map(([key, item]) => [key, String(item)]));
};

const safeDate = (value: unknown) => {
  if (!value) return '';
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 10);
  return date.toISOString().slice(0, 10);
};

const mapFolder = (value: unknown, project?: Project): Folder => {
  const record = toRecord(value);
  const entities = parseEntities(record.entities);
  return {
    id: String(record.id || ''),
    name: String(record.name || 'Untitled folder'),
    description: String(record.description || ''),
    status: normalizeFolderStatus(record.status),
    projectId: String(record.project_id || record.projectId || project?.id || ''),
    projectName: String(record.project_name || record.projectName || project?.name || ''),
    createdBy: String(record.created_by_name || record.created_by || record.createdBy || ''),
    createdAt: safeDate(record.created_at || record.createdAt),
    accessLevel: String(record.access_level || record.accessLevel || '').toLowerCase().includes('read') ? 'view' : 'full',
    entities,
    raw: value,
  };
};

const mapProject = (value: unknown): Project => {
  const record = toRecord(value);
  const folders = Array.isArray(record.folders) ? record.folders : [];
  return {
    id: String(record.id || ''),
    name: String(record.name || 'Untitled project'),
    description: String(record.description || ''),
    status: normalizeProjectStatus(record.status),
    createdBy: String(record.created_by_name || record.created_by || record.createdBy || ''),
    createdAt: safeDate(record.created_at || record.createdAt),
    folderCount: folders.length,
    accessLevel: String(record.user_access_level || record.accessLevel || ''),
    raw: value,
  };
};

const mapSession = (value: unknown, folder: Folder): Session => {
  const record = toRecord(unwrapData<unknown>(value));
  return {
    id: String(record.id || ''),
    folderId: String(record.folder_id || folder.id),
    folderName: folder.name,
    projectName: folder.projectName,
    status: String(record.status || 'ACTIVE').toUpperCase() === 'ACTIVE' ? 'active' : 'inactive',
    createdAt: safeDate(record.created_at),
    appName: String(record.app_name || ''),
    entities: parseEntities(record.entities),
    raw: value,
  };
};

const filesFromEntities = (folder: Folder): UploadedFile[] => {
  const files = folder.entities?.files || {};
  return Object.entries(files).map(([id, name]) => ({
    id,
    name,
    size: 0,
    type: name.includes('.') ? name.split('.').pop() || 'file' : 'file',
    status: 'uploaded',
    uploadedAt: folder.createdAt,
  }));
};

const normalizeRows = (rows: Array<Record<string, string | number>> = []) =>
  rows.map((row) =>
    Object.fromEntries(
      Object.entries(row).map(([key, value]) => [
        key,
        typeof value === 'number' || typeof value === 'string' ? value : String(value ?? ''),
      ]),
    ),
  );

export function AppStateProvider({ children }: { children: ReactNode }) {
  const { user, isAuthenticated } = useAuth();
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [selectedFolder, setSelectedFolder] = useState<Folder | null>(null);
  const [activeSession, setActiveSession] = useState<Session | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isServerOnline, setIsServerOnline] = useState(true);
  const [projectList, setProjectList] = useState<Project[]>([]);
  const [folderList, setFolderList] = useState<Folder[]>([]);
  const [fileList, setFileList] = useState<UploadedFile[]>([]);
  const [sessionList, setSessionList] = useState<Session[]>([]);
  const [tables, setTables] = useState<DataTable[]>([]);
  const [charts, setCharts] = useState<ChartWidget[]>([]);
  const [reports, setReports] = useState<GeneratedReport[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const refreshProjects = useCallback(async () => {
    if (!user?.id) {
      setProjectList([]);
      setFolderList([]);
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);
    try {
      const rawProjects = await fetchProjectsForUser(user.id);
      const mappedProjects = rawProjects.map(mapProject).filter((project) => project.status !== 'Deleted');
      const mappedFolders = rawProjects.flatMap((rawProject) => {
        const project = mapProject(rawProject);
        const folderValues = Array.isArray(toRecord(rawProject).folders) ? (toRecord(rawProject).folders as unknown[]) : [];
        return folderValues.map((folder) => mapFolder(folder, project)).filter((folder) => folder.status !== 'Deleted');
      });

      setProjectList(mappedProjects);
      setFolderList(mappedFolders);

      setSelectedProject((current) => {
        if (!current) return current;
        return mappedProjects.find((project) => project.id === current.id) || null;
      });
      setSelectedFolder((current) => {
        if (!current) return current;
        return mappedFolders.find((folder) => folder.id === current.id) || null;
      });
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to load projects');
    } finally {
      setIsLoading(false);
    }
  }, [user?.id]);

  useEffect(() => {
    if (!isAuthenticated) {
      setProjectList([]);
      setFolderList([]);
      setSelectedProject(null);
      setSelectedFolder(null);
      setActiveSession(null);
      setFileList([]);
      setTables([]);
      return;
    }
    void refreshProjects();
  }, [isAuthenticated, refreshProjects]);

  const loadTablesForFolder = useCallback(async (folder: Folder) => {
    const uploadedTables = folder.entities?.tables || {};
    const tableTypes: Record<string, 'uploaded' | 'agent_created'> = {};
    Object.keys(uploadedTables).forEach((tableId) => {
      tableTypes[tableId] = 'uploaded';
    });

    let mergedTables = { ...uploadedTables };
    try {
      const dbTables = await fetchAllFolderTables(folder.id);
      if (dbTables.tables) {
        mergedTables = { ...mergedTables, ...dbTables.tables };
      }
      if (dbTables.table_types) {
        Object.assign(tableTypes, dbTables.table_types);
      }
    } catch {
      // Folder entities are still enough to render uploaded tables.
    }

    const nextTables = Object.entries(mergedTables).map(([id, name]) => ({
      id,
      name,
      source: tableTypes[id] || 'uploaded',
      columns: [],
      rows: [],
      rowCount: 0,
      hasMore: true,
      page: 0,
    })) satisfies DataTable[];

    setTables(nextTables);
    return nextTables;
  }, []);

  const loadSessionForFolder = useCallback(
    async (folder: Folder) => {
      if (!user?.id) return null;
      try {
        const rawSession = await fetchSessionByFolderAndUser(folder.id, user.id);
        const record = toRecord(unwrapData<unknown>(rawSession));
        if (!record.id) {
          setActiveSession(null);
          return null;
        }
        const mappedSession = mapSession(record, folder);
        setActiveSession(mappedSession);
        setSessionList((current) => {
          const withoutCurrent = current.filter((session) => session.id !== mappedSession.id);
          return [...withoutCurrent, mappedSession];
        });
        sessionStorage.setItem('sessionId', mappedSession.id);
        return mappedSession;
      } catch {
        setActiveSession(null);
        return null;
      }
    },
    [user?.id],
  );

  const applyFolderContext = useCallback(
    async (folder: Folder) => {
      const project = projectList.find((item) => item.id === folder.projectId) || selectedProject;
      setSelectedFolder(folder);
      if (project) setSelectedProject(project);
      sessionStorage.setItem('folderId', folder.id);
      if (folder.projectId) sessionStorage.setItem('projectId', folder.projectId);
      sessionStorage.setItem('folderData', JSON.stringify(folder.raw || folder));
      setFileList(filesFromEntities(folder));
      await loadSessionForFolder(folder);
      await loadTablesForFolder(folder);
    },
    [loadSessionForFolder, loadTablesForFolder, projectList, selectedProject],
  );

  const loadFolderContext = useCallback(
    async (folderId: string) => {
      const localFolder = folderList.find((folder) => folder.id === folderId);
      if (localFolder) {
        await applyFolderContext(localFolder);
        return localFolder;
      }

      try {
        const response = await fetchFolderById(folderId);
        const rawFolder = unwrapData<unknown>(response);
        const folder = mapFolder(rawFolder, selectedProject || undefined);
        await applyFolderContext(folder);
        setFolderList((current) => (current.some((item) => item.id === folder.id) ? current : [...current, folder]));
        return folder;
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Failed to load folder');
        return null;
      }
    },
    [applyFolderContext, folderList, selectedProject],
  );

  const selectProject = useCallback((project: Project | null) => {
    setSelectedProject(project);
    setSelectedFolder(null);
    setActiveSession(null);
    setFileList([]);
    setTables([]);
    if (project) sessionStorage.setItem('projectId', project.id);
    else sessionStorage.removeItem('projectId');
  }, []);

  const selectFolder = useCallback(
    (folder: Folder | null) => {
      if (!folder) {
        setSelectedFolder(null);
        setActiveSession(null);
        setFileList([]);
        setTables([]);
        sessionStorage.removeItem('folderId');
        return;
      }
      void applyFolderContext(folder);
    },
    [applyFolderContext],
  );

  const loadTablePreview = useCallback(
    async (tableId: string, page = 1, limit = 50) => {
      if (!user?.id || !selectedFolder) return null;
      setTables((current) =>
        current.map((table) => (table.id === tableId ? { ...table, isLoading: true } : table)),
      );
      try {
        const result = await fetchTablePreview({
          tableName: tableId,
          conversationId: activeSession?.id || 'preview',
          userId: user.id,
          pageNo: page,
          limitNo: limit,
          folderId: selectedFolder.id,
        });
        let updatedTable: DataTable | null = null;
        setTables((current) =>
          current.map((table) => {
            if (table.id !== tableId) return table;
            const rows = normalizeRows(result.data);
            updatedTable = {
              ...table,
              columns: result.columns || table.columns,
              rows: page > 1 ? [...table.rows, ...rows] : rows,
              rowCount: result.total || rows.length,
              isLoading: false,
              page,
              hasMore: (result.total || rows.length) > (page > 1 ? table.rows.length + rows.length : rows.length),
            };
            return updatedTable;
          }),
        );
        return updatedTable;
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Failed to load table preview');
        setTables((current) =>
          current.map((table) => (table.id === tableId ? { ...table, isLoading: false, hasMore: false } : table)),
        );
        return null;
      }
    },
    [activeSession?.id, selectedFolder, user?.id],
  );

  const ensureSession = useCallback(async () => {
    if (activeSession) return activeSession;
    if (!selectedFolder || !user?.id) return null;
    const created = await createSessionRecord({
      folderId: selectedFolder.id,
      createdBy: user.id,
    });
    const mapped = mapSession(created, selectedFolder);
    setActiveSession(mapped);
    setSessionList((current) => [...current.filter((session) => session.id !== mapped.id), mapped]);
    sessionStorage.setItem('sessionId', mapped.id);
    return mapped;
  }, [activeSession, selectedFolder, user?.id]);

  const toggleSidebar = useCallback(() => {
    setIsSidebarOpen((value) => !value);
  }, []);

  const createProject = useCallback(
    async (name: string, description: string, status: Project['status']) => {
      if (!user?.id) return null;
      const rawProject = await createProjectRecord({ name, description, status, createdBy: user.id });
      const mappedProject = mapProject(rawProject);
      setProjectList((current) => [...current, mappedProject]);
      setSelectedProject(mappedProject);
      await refreshProjects();
      return mappedProject;
    },
    [refreshProjects, user?.id],
  );

  const updateProject = useCallback(
    async (id: string, updates: Partial<Project>) => {
      await updateProjectRecord(id, updates);
      setProjectList((current) => current.map((project) => (project.id === id ? { ...project, ...updates } : project)));
      setSelectedProject((current) => (current?.id === id ? { ...current, ...updates } : current));
      await refreshProjects();
    },
    [refreshProjects],
  );

  const deleteProject = useCallback(
    async (id: string) => {
      await deleteProjectRecord(id);
      setProjectList((current) => current.filter((project) => project.id !== id));
      setFolderList((current) => current.filter((folder) => folder.projectId !== id));
      if (selectedProject?.id === id) selectProject(null);
      await refreshProjects();
    },
    [refreshProjects, selectProject, selectedProject?.id],
  );

  const createFolder = useCallback(
    async (name: string, description: string, projectId: string) => {
      if (!user?.id) return null;
      const project = projectList.find((item) => item.id === projectId);
      const rawFolder = await createFolderRecord({ name, description, projectId, createdBy: user.id });
      const mappedFolder = mapFolder(rawFolder, project);
      setFolderList((current) => [...current, mappedFolder]);
      await refreshProjects();
      return mappedFolder;
    },
    [projectList, refreshProjects, user?.id],
  );

  const updateFolder = useCallback(
    async (id: string, updates: Partial<Folder>) => {
      await updateFolderRecord(id, updates);
      setFolderList((current) => current.map((folder) => (folder.id === id ? { ...folder, ...updates } : folder)));
      setSelectedFolder((current) => (current?.id === id ? { ...current, ...updates } : current));
      await refreshProjects();
    },
    [refreshProjects],
  );

  const deleteFolder = useCallback(
    async (id: string) => {
      await deleteFolderRecord(id);
      setFolderList((current) => current.filter((folder) => folder.id !== id));
      if (selectedFolder?.id === id) selectFolder(null);
      await refreshProjects();
    },
    [refreshProjects, selectFolder, selectedFolder?.id],
  );

  const addFiles = useCallback((newFiles: UploadedFile[]) => {
    setFileList((current) => [...current, ...newFiles]);
  }, []);

  const removeFile = useCallback((id: string) => {
    setFileList((current) => current.filter((file) => file.id !== id));
  }, []);

  const addChart = useCallback((chart: ChartWidget) => {
    setCharts((current) => [...current, chart]);
  }, []);

  const removeChart = useCallback((id: string) => {
    setCharts((current) => current.filter((chart) => chart.id !== id));
  }, []);

  const addReport = useCallback((report: GeneratedReport) => {
    setReports((current) => [...current, report]);
  }, []);

  const getProjectFolders = useCallback(
    (projectId: string) => folderList.filter((folder) => folder.projectId === projectId),
    [folderList],
  );

  const value = useMemo<AppStateContextValue>(
    () => ({
      selectedProject,
      selectedFolder,
      activeSession,
      isSidebarOpen,
      isServerOnline,
      projectList,
      folderList,
      fileList,
      sessionList,
      tables,
      charts,
      reports,
      isLoading,
      errorMessage,
      setIsLoading,
      setIsServerOnline,
      setActiveSession,
      selectProject,
      selectFolder,
      loadFolderContext,
      refreshProjects,
      ensureSession,
      loadTablesForFolder,
      loadTablePreview,
      toggleSidebar,
      createProject,
      updateProject,
      deleteProject,
      createFolder,
      updateFolder,
      deleteFolder,
      addFiles,
      removeFile,
      addChart,
      removeChart,
      addReport,
      getProjectFolders,
    }),
    [
      activeSession,
      addChart,
      addFiles,
      addReport,
      charts,
      createFolder,
      createProject,
      deleteFolder,
      deleteProject,
      ensureSession,
      errorMessage,
      fileList,
      folderList,
      getProjectFolders,
      isLoading,
      isServerOnline,
      isSidebarOpen,
      loadFolderContext,
      loadTablePreview,
      loadTablesForFolder,
      projectList,
      refreshProjects,
      removeChart,
      removeFile,
      reports,
      selectFolder,
      selectProject,
      selectedFolder,
      selectedProject,
      sessionList,
      tables,
      toggleSidebar,
      updateFolder,
      updateProject,
    ],
  );

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState() {
  const context = useContext(AppStateContext);
  if (!context) {
    throw new Error('useAppState must be used within AppStateProvider');
  }
  return context;
}

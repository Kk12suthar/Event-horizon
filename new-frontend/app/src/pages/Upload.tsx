import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Upload as UploadIcon, X, FileSpreadsheet, ChevronDown, ChevronUp, Trash2, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { OfflineState } from '@/components/OfflineState';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { useAppState } from '@/hooks/useAppState';
import { useAuth } from '@/hooks/useAuth';
import { createFileRecord, createId, getUploadWebSocketUrl, updateFileStatus } from '@/lib/api';
import type { UploadedFile } from '@/types';

interface UploadSocketResult {
  sessionId?: string;
  createdTables: Record<string, string>;
  files: Record<string, string>;
}

export function Upload() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const appState = useAppState();
  const { user } = useAuth();
  const { selectedFolder, selectedProject, fileList, isServerOnline } = appState;
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStage, setUploadStage] = useState<'idle' | 'uploading' | 'creating' | 'complete'>('idle');
  const [sessionExpanded, setSessionExpanded] = useState(false);
  const [showDeleteFile, setShowDeleteFile] = useState<string | null>(null);
  const [managerCollapsed, setManagerCollapsed] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  useEffect(() => {
    const folderId = searchParams.get('folderId');
    if (folderId && selectedFolder?.id !== folderId) {
      void appState.loadFolderContext(folderId);
    }
  }, [appState, searchParams, selectedFolder?.id]);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const onDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = Array.from(e.dataTransfer.files).filter(f =>
      f.name.endsWith('.csv') || f.name.endsWith('.xls') || f.name.endsWith('.xlsx')
    );
    if (files.length) setSelectedFiles(prev => [...prev, ...files]);
  }, []);

  const onFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length) setSelectedFiles(prev => [...prev, ...files]);
  }, []);

  const removeFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const sendFileChunks = async (socket: WebSocket, file: File, fileIndex: number, onBytes: (bytes: number) => void) => {
    const chunkSize = 1024 * 1024;
    let offset = 0;
    let chunkIndex = 0;

    while (offset < file.size) {
      const slice = file.slice(offset, offset + chunkSize);
      offset += chunkSize;

      await new Promise<void>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (event) => {
          if (socket.readyState !== WebSocket.OPEN) {
            reject(new Error('Upload connection closed'));
            return;
          }
          const binary = String(event.target?.result || '');
          socket.send(JSON.stringify({
            type: 'data',
            data: btoa(binary),
            encoding: 'base64',
            fileIndex,
            chunkIndex,
          }));
          onBytes(slice.size);
          resolve();
        };
        reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
        reader.readAsBinaryString(slice);
      });

      chunkIndex += 1;
    }

    socket.send(JSON.stringify({ type: 'file_complete', fileIndex }));
  };

  const uploadWithSocket = async (sessionId: string | null, fileIds: string[]) => {
    if (!selectedFolder || !user) throw new Error('Select a folder before uploading files');

    return new Promise<UploadSocketResult>((resolve, reject) => {
      const socket = new WebSocket(getUploadWebSocketUrl());
      const result: UploadSocketResult = { sessionId: sessionId || undefined, createdTables: {}, files: {} };
      let settled = false;

      const fail = (error: Error) => {
        if (settled) return;
        settled = true;
        socket.close();
        reject(error);
      };

      socket.onerror = () => fail(new Error('Upload websocket connection failed'));
      socket.onclose = () => {
        if (!settled) fail(new Error('Upload websocket closed before processing completed'));
      };
      socket.onmessage = (event) => {
        const data = JSON.parse(event.data) as Record<string, unknown>;
        if (data.type === 'error') {
          fail(new Error(String(data.message || 'Upload failed')));
          return;
        }
        if (data.type === 'table_progress') {
          setUploadStage('creating');
          setUploadProgress(Number(data.progress || 0));
        }
        if (data.type === 'session_created') {
          result.sessionId = String(data.sessionId || sessionId || '');
          result.createdTables = (data.createdTables || {}) as Record<string, string>;
          result.files = (data.files || {}) as Record<string, string>;
        }
        if (data.type === 'all_tables_created') {
          if (settled) return;
          settled = true;
          socket.close();
          resolve(result);
        }
      };

      socket.onopen = () => {
        void (async () => {
          const totalSize = selectedFiles.reduce((sum, file) => sum + file.size, 0);
          let totalBytesSent = 0;

          socket.send(JSON.stringify({
            type: 'start_upload',
            totalFiles: selectedFiles.length,
            userId: user.id,
            sessionId,
          }));

          for (let index = 0; index < selectedFiles.length; index += 1) {
            const file = selectedFiles[index];
            socket.send(JSON.stringify({
              type: 'metadata',
              fileName: file.name,
              fileIndex: index,
              projectId: selectedFolder.projectId || selectedProject?.id || '',
              folderId: selectedFolder.id,
              userId: user.id,
              fileId: fileIds[index],
              sessionId,
            }));

            await sendFileChunks(socket, file, index, (bytes) => {
              totalBytesSent += bytes;
              const progress = totalSize > 0 ? Math.min(100, Math.round((totalBytesSent / totalSize) * 100)) : 100;
              setUploadProgress(progress);
            });
          }

          setUploadStage('creating');
          setUploadProgress(0);
          socket.send(JSON.stringify({ type: 'process_files', sessionId }));
        })().catch(fail);
      };
    });
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0 || !selectedFolder || !user) return;
    setIsUploading(true);
    setUploadStage('uploading');
    setUploadProgress(0);
    setUploadError(null);

    const createdFileIds: string[] = [];
    try {
      const session = await appState.ensureSession();
      const sessionId = session?.id || null;

      for (const file of selectedFiles) {
        const fileId = createId();
        createdFileIds.push(fileId);
        await createFileRecord({
          id: fileId,
          name: file.name.replace(/[\\?%*:|"<>]/g, '_').slice(0, 50),
          originalName: file.name,
          uploadedBy: user.id,
          parentFolderId: selectedFolder.id,
          status: 'UPLOADED',
        });
      }

      const result = await uploadWithSocket(sessionId, createdFileIds);
      const existingEntities = selectedFolder.entities || {};
      const updatedEntities = {
        ...existingEntities,
        tables: { ...(existingEntities.tables || {}), ...result.createdTables },
        files: { ...(existingEntities.files || {}), ...result.files },
      };
      await appState.updateFolder(selectedFolder.id, {
        entities: updatedEntities,
      });
      await appState.loadTablesForFolder({ ...selectedFolder, entities: updatedEntities });

      const newFiles: UploadedFile[] = selectedFiles.map((file, index) => ({
        id: createdFileIds[index],
        name: file.name,
        size: file.size,
        type: file.name.split('.').pop() || 'unknown',
        status: 'uploaded' as const,
        uploadedAt: new Date().toISOString().split('T')[0],
      }));
      appState.addFiles(newFiles);
      setSelectedFiles([]);
      setUploadStage('complete');
      setUploadProgress(100);
      window.setTimeout(() => setUploadStage('idle'), 3000);
    } catch (error) {
      setUploadStage('idle');
      setUploadError(error instanceof Error ? error.message : 'Upload failed');
      await Promise.all(createdFileIds.map((id) => updateFileStatus(id, 'FAILED').catch(() => undefined)));
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeleteFile = () => {
    if (showDeleteFile) {
      appState.removeFile(showDeleteFile);
      setShowDeleteFile(null);
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (!isServerOnline) {
    return (
      <div className="p-6">
        <OfflineState onRetry={() => appState.setIsServerOnline(true)} />
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 overflow-hidden bg-[#000000] max-lg:flex-col">
      <div className={`${managerCollapsed ? 'w-12' : 'w-[320px]'} flex min-h-0 flex-shrink-0 flex-col bg-[#151515]/95 border-r border-[#2E2E2E] transition-all duration-200 max-lg:h-[260px] max-lg:w-full max-lg:border-b max-lg:border-r-0`}>
        <div className="flex items-center justify-between p-3 border-b border-[#2E2E2E]">
          {!managerCollapsed && <h3 className="text-sm font-semibold text-white">Files</h3>}
          <button
            onClick={() => setManagerCollapsed(!managerCollapsed)}
            className="w-6 h-6 flex items-center justify-center rounded text-[#8C8C8C] hover:text-white hover:bg-[#1E1E1E]"
          >
            {managerCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
          </button>
        </div>
        {!managerCollapsed && (
          <div className="min-h-0 flex-1 overflow-y-auto py-2">
            {fileList.length === 0 ? (
              <div className="p-4 text-center">
                <p className="text-xs text-[#8C8C8C]">No files uploaded yet</p>
              </div>
            ) : (
              fileList.map(file => (
                <div key={file.id} className="flex items-center justify-between px-3 py-2.5 hover:bg-[#1E1E1E] group">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileSpreadsheet className="w-4 h-4 text-[#E4E4E7] flex-shrink-0" />
                    <div className="min-w-0">
                      <p className="text-sm text-white truncate">{file.name}</p>
                      <p className="text-[10px] text-[#8C8C8C]">{formatSize(file.size)}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setShowDeleteFile(file.id)}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded text-[#8C8C8C] hover:text-[#F97066] transition-all"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      <div className="flex-1 min-w-0 overflow-y-auto p-6">
        <div className="mx-auto flex w-full max-w-6xl flex-col">
          <div className="mb-2">
            <h1 className="text-xl font-bold text-white">Upload Data</h1>
            {selectedFolder && (
              <p className="text-xs text-[#B8B8B8] mt-1">
                {selectedProject?.name} / {selectedFolder.name}
              </p>
            )}
          </div>

          <p className="text-sm text-[#B8B8B8] mb-6">
            Upload CSV, XLS, or XLSX files. Supported formats: .csv, .xls, .xlsx
          </p>
          {!selectedFolder && (
            <div className="mb-4 rounded-lg border border-[#F59E0B]/30 bg-[#F59E0B]/10 px-4 py-3 text-sm text-[#F59E0B]">
              Select a project folder before uploading data.
            </div>
          )}

          <div
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            className={`border-2 border-dashed rounded-2xl min-h-[300px] w-full flex flex-col items-center justify-center px-6 transition-colors shadow-[0_18px_60px_rgba(0,0,0,0.18)] ${
              isDragOver ? 'border-[#c16e43] bg-[#c16e43]/10' : 'border-[#2E2E2E] bg-[#151515]/70 hover:border-[#525252]'
            }`}
          >
            <UploadIcon className="w-12 h-12 text-[#E4E4E7] mb-3" />
            <h3 className="text-lg font-semibold text-white">Drop files here</h3>
            <p className="text-sm text-[#B8B8B8] mt-1">or click to browse</p>
            <input
              type="file"
              accept=".csv,.xls,.xlsx"
              multiple
              onChange={onFileSelect}
              className="hidden"
              id="file-input"
            />
            <label htmlFor="file-input">
              <Button variant="outline" className="mt-4 border-[#2E2E2E] text-[#B8B8B8] hover:bg-[#1E1E1E] hover:text-white" asChild>
                <span>{fileList.length > 0 ? 'Select More Files' : 'Select Files'}</span>
              </Button>
            </label>
          </div>

          {selectedFiles.length > 0 && (
            <div className="mt-6 space-y-2">
              <h4 className="text-sm font-semibold text-white">Selected Files</h4>
              {selectedFiles.map((file, i) => (
                <div key={i} className="flex items-center justify-between bg-[#151515] border border-[#2E2E2E] rounded-lg px-4 py-3">
                  <div className="flex items-center gap-3">
                    <FileSpreadsheet className="w-5 h-5 text-[#E4E4E7]" />
                    <div>
                      <p className="text-sm text-white">{file.name}</p>
                      <p className="text-xs text-[#8C8C8C]">{formatSize(file.size)}</p>
                    </div>
                  </div>
                  <button onClick={() => removeFile(i)} className="p-1 rounded text-[#8C8C8C] hover:text-[#F97066]">
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {uploadStage !== 'idle' && (
            <div className="mt-6 p-4 bg-[#151515] border border-[#2E2E2E] rounded-xl">
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-semibold text-white">
                  {uploadStage === 'uploading' ? 'Uploading...' :
                   uploadStage === 'creating' ? 'Creating tables...' :
                   'Complete'}
                </h4>
                {uploadStage === 'uploading' && <span className="text-xs text-[#B8B8B8]">{uploadProgress}%</span>}
              </div>
              {uploadStage === 'uploading' && <Progress value={uploadProgress} className="h-1.5 bg-[#2E2E2E]" />}
              {uploadStage === 'creating' && <div className="flex items-center gap-2"><Loader2 className="w-4 h-4 text-[#E4E4E7] animate-spin" /><span className="text-xs text-[#B8B8B8]">Processing data...</span></div>}
              {uploadStage === 'complete' && <div className="flex items-center gap-2 text-[#22C55E]"><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg><span className="text-xs">Upload complete!</span></div>}
            </div>
          )}

          {uploadError && (
            <div className="mt-4 rounded-lg border border-[#F97066]/30 bg-[#F97066]/10 px-4 py-3 text-sm text-[#F97066]">
              {uploadError}
            </div>
          )}

          <div className="mt-6">
            <button
              onClick={() => setSessionExpanded(!sessionExpanded)}
              className="flex items-center gap-2 text-sm font-medium text-[#B8B8B8] hover:text-white"
            >
              {sessionExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              Session
              {appState.activeSession && <span className="text-[10px] px-1.5 py-0.5 bg-[#22C55E]/10 text-[#22C55E] rounded-full">Active</span>}
            </button>
            {sessionExpanded && (
              <div className="mt-2 p-3 bg-[#151515] border border-[#2E2E2E] rounded-lg">
                {appState.activeSession ? (
                  <div className="space-y-1 text-xs">
                    <p className="text-[#8C8C8C]">ID: <span className="text-white font-mono">{appState.activeSession.id}</span></p>
                    <p className="text-[#8C8C8C]">Folder: <span className="text-white">{appState.activeSession.folderName}</span></p>
                  </div>
                ) : (
                  <p className="text-xs text-[#8C8C8C]">No active session. Upload files to create one.</p>
                )}
              </div>
            )}
          </div>

          <div className="mt-6 space-y-3">
            <Button
              onClick={handleUpload}
              disabled={!selectedFolder || selectedFiles.length === 0 || isUploading}
              className="h-11 w-full bg-[#c16e43] font-semibold text-[#0A0A0A] hover:bg-[#d08a5e] disabled:opacity-50"
            >
              {isUploading ? (
                uploadStage === 'uploading' ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Uploading...</> :
                uploadStage === 'creating' ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Creating Tables...</> :
                'Uploading...'
              ) : `Upload ${selectedFiles.length > 0 ? `(${selectedFiles.length})` : ''}`}
            </Button>

            {uploadStage === 'complete' && (
              <Button
                variant="outline"
                onClick={() => selectedFolder && navigate(`/app/transform?folderId=${selectedFolder.id}`)}
                className="w-full h-11 border-[#2E2E2E] text-[#B8B8B8] hover:bg-[#1E1E1E] hover:text-white"
              >
                {appState.activeSession ? 'Continue Transformation' : 'Start Transformation'}
              </Button>
            )}
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={!!showDeleteFile}
        onOpenChange={() => setShowDeleteFile(null)}
        title="Delete File?"
        description="This file will be permanently removed."
        onConfirm={handleDeleteFile}
      />
    </div>
  );
}

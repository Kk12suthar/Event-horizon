import { useCallback, useEffect, useRef, useState } from 'react';
import {
  createFileRecord,
  createId,
  fetchUploadQuota,
  getUploadAccessToken,
  getUploadWebSocketUrl,
  updateFileStatus,
} from '../lib/api';
import type {
  ChatMessage,
  DataTable,
  Folder,
  Session,
  UploadedFile,
  User,
} from '../types';

/** Lifecycle of an upload, surfaced to the UI for progress/skeleton rendering. */
export type UploadStage = 'idle' | 'uploading' | 'creating' | 'complete';

/** Client-side allowlist (server remains authoritative). */
export const ALLOWED_UPLOAD_EXTENSIONS = ['.csv', '.xls', '.xlsx'] as const;

/** True when a file name ends with an allowed spreadsheet extension. */
export function isAllowedUploadFile(fileName: string): boolean {
  const lower = fileName.toLowerCase();
  return ALLOWED_UPLOAD_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

interface UploadSocketResult {
  sessionId?: string;
  createdTables: Record<string, string>;
  files: Record<string, string>;
}

export interface UseFolderUpload {
  /** Validate, then stream the given files over the existing upload WebSocket. */
  upload: (files: File[]) => Promise<void>;
  /** Byte/processing progress in [0, 100]. */
  progress: number;
  /** Current lifecycle stage. */
  stage: UploadStage;
  /** Last error message, or null. */
  error: string | null;
}

export interface UseFolderUploadContext {
  folder: Folder | null;
  user: User | null;
  ensureSession: () => Promise<Session | null>;
  /** Persist merged folder entities (tables/files) after creation. */
  updateFolder: (id: string, updates: Partial<Folder>) => Promise<void>;
  /** Reload the folder's tables so pipeline gating can re-derive. */
  loadTablesForFolder: (folder: Folder) => Promise<DataTable[]>;
  /** Append the freshly uploaded files to the shared file list. */
  addFiles: (files: UploadedFile[]) => void;
  /** Called after tables are created and entities merged (e.g. to refresh artifacts). */
  onTablesCreated?: (folder: Folder) => void;
  /** Stream progress/status updates into the shared Agent Activity trail. */
  onActivity?: (message: ChatMessage) => void;
}

/**
 * Folds the legacy Upload page's WebSocket protocol into a reusable hook so the
 * Workspace composer can upload inside the conversation.
 *
 * Behavior (see design.md "useFolderUpload" + Requirements 6.4, 6.5):
 *   - Enforces the `.csv/.xls/.xlsx` allowlist client-side before sending.
 *   - Reuses the exact protocol: `start_upload` -> per-file `metadata` -> chunked
 *     `data` (base64, 1MB) -> `file_complete` -> `process_files`, listening for
 *     `table_progress`, `session_created`, and `all_tables_created`.
 *   - Streams progress/status into the shared activity trail via `onActivity`.
 *   - On `all_tables_created`, merges `entities` via `updateFolder`, reloads the
 *     folder tables, then calls `onTablesCreated` so gating can flip.
 *
 * Loop invariant (chunk loop): bytes sent increase monotonically; `progress`
 * stays within [0, 100] and never decreases during a single file's transfer.
 */
export function useFolderUpload(ctx: UseFolderUploadContext): UseFolderUpload {
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState<UploadStage>('idle');
  const [error, setError] = useState<string | null>(null);

  // Keep the latest context in a ref so the stable `upload` callback always
  // sees current folder/user/session helpers without re-creating itself. The
  // ref is updated in an effect (not during render) to satisfy the rules of
  // React; the callbacks that read it only run after commit (async/handlers).
  const ctxRef = useRef(ctx);
  useEffect(() => {
    ctxRef.current = ctx;
  });

  const emitActivity = useCallback((content: string) => {
    ctxRef.current.onActivity?.({
      id: createId(),
      type: 'activity',
      content,
      timestamp: new Date().toISOString(),
    });
  }, []);

  const sendFileChunks = useCallback(
    async (socket: WebSocket, file: File, fileIndex: number, onBytes: (bytes: number) => void) => {
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
            socket.send(
              JSON.stringify({
                type: 'data',
                data: btoa(binary),
                encoding: 'base64',
                fileIndex,
                chunkIndex,
              }),
            );
            onBytes(slice.size);
            resolve();
          };
          reader.onerror = () => reject(new Error(`Failed to read ${file.name}`));
          reader.readAsBinaryString(slice);
        });

        chunkIndex += 1;
      }

      socket.send(JSON.stringify({ type: 'file_complete', fileIndex }));
    },
    [],
  );

  const uploadWithSocket = useCallback(
    (files: File[], sessionId: string | null, fileIds: string[]): Promise<UploadSocketResult> => {
      const { folder, user } = ctxRef.current;
      if (!folder || !user) throw new Error('Select a folder before uploading files');

      return new Promise<UploadSocketResult>((resolve, reject) => {
        const socket = new WebSocket(getUploadWebSocketUrl());
        const result: UploadSocketResult = { sessionId: sessionId || undefined, createdTables: {}, files: {} };
        let settled = false;

        const fail = (err: Error) => {
          if (settled) return;
          settled = true;
          socket.close();
          reject(err);
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
            setStage('creating');
            setProgress(Number(data.progress || 0));
            emitActivity(`Creating tables… ${Number(data.progress || 0)}%`);
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
            const totalSize = files.reduce((sum, file) => sum + file.size, 0);
            let totalBytesSent = 0;

            socket.send(
              JSON.stringify({
                type: 'start_upload',
                totalFiles: files.length,
                userId: user.id,
                accessToken: getUploadAccessToken(),
                sessionId,
              }),
            );

            for (let index = 0; index < files.length; index += 1) {
              const file = files[index];
              emitActivity(`Uploading ${file.name}…`);
              socket.send(
                JSON.stringify({
                  type: 'metadata',
                  fileName: file.name,
                  fileIndex: index,
                  projectId: folder.projectId || '',
                  folderId: folder.id,
                  userId: user.id,
                  fileId: fileIds[index],
                  sessionId,
                }),
              );

              await sendFileChunks(socket, file, index, (bytes) => {
                totalBytesSent += bytes;
                const pct = totalSize > 0 ? Math.min(100, Math.round((totalBytesSent / totalSize) * 100)) : 100;
                setProgress(pct);
              });
            }

            setStage('creating');
            setProgress(0);
            emitActivity('Processing uploaded files…');
            socket.send(JSON.stringify({ type: 'process_files', sessionId }));
          })().catch(fail);
        };
      });
    },
    [emitActivity, sendFileChunks],
  );

  const upload = useCallback(
    async (files: File[]) => {
      const { folder, user, ensureSession, updateFolder, loadTablesForFolder, addFiles, onTablesCreated } =
        ctxRef.current;

      if (!folder || !user) {
        setError('Select a folder before uploading files');
        return;
      }

      // Client-side allowlist enforcement (server remains authoritative).
      const allowed = files.filter((file) => isAllowedUploadFile(file.name));
      const rejected = files.filter((file) => !isAllowedUploadFile(file.name));
      if (rejected.length > 0) {
        const names = rejected.map((f) => f.name).join(', ');
        const message = `Unsupported file type: ${names}. Only .csv, .xls, and .xlsx are allowed.`;
        setError(message);
        emitActivity(message);
      }
      if (allowed.length === 0) {
        if (rejected.length === 0) setError('No files selected for upload');
        return;
      }

      setStage('uploading');
      setProgress(0);
      setError(null);

      const createdFileIds: string[] = [];
      try {
        const quota = await fetchUploadQuota();
        const requestedBytes = allowed.reduce((sum, file) => sum + file.size, 0);
        const oversized = allowed.find((file) => file.size > quota.limits.max_file_bytes);
        const mib = (bytes: number) => `${Math.floor(bytes / (1024 * 1024))} MiB`;
        if (oversized) {
          throw new Error(`${oversized.name} exceeds the ${mib(quota.limits.max_file_bytes)} per-file limit.`);
        }
        if (allowed.length > quota.remaining.file_count) {
          throw new Error(`Only ${quota.remaining.file_count} upload slot(s) remain for this account.`);
        }
        if (requestedBytes > quota.remaining.total_bytes) {
          throw new Error(`This upload exceeds the ${mib(quota.remaining.total_bytes)} remaining account storage.`);
        }

        const session = await ensureSession();
        const sessionId = session?.id || null;

        for (const file of allowed) {
          const fileId = createId();
          createdFileIds.push(fileId);
          await createFileRecord({
            id: fileId,
            name: file.name.replace(/[\\?%*:|"<>]/g, '_').slice(0, 50),
            originalName: file.name,
            uploadedBy: user.id,
            parentFolderId: folder.id,
            sizeBytes: file.size,
            status: 'UPLOADED',
          });
        }

        const result = await uploadWithSocket(allowed, sessionId, createdFileIds);

        const existingEntities = folder.entities || {};
        const updatedEntities = {
          ...existingEntities,
          tables: { ...(existingEntities.tables || {}), ...result.createdTables },
          files: { ...(existingEntities.files || {}), ...result.files },
        };
        await updateFolder(folder.id, { entities: updatedEntities });

        const mergedFolder: Folder = { ...folder, entities: updatedEntities };
        await loadTablesForFolder(mergedFolder);

        const newFiles: UploadedFile[] = allowed.map((file, index) => ({
          id: createdFileIds[index],
          name: file.name,
          size: file.size,
          type: file.name.split('.').pop() || 'unknown',
          status: 'uploaded' as const,
          uploadedAt: new Date().toISOString().split('T')[0],
        }));
        addFiles(newFiles);

        setStage('complete');
        setProgress(100);
        emitActivity('Upload complete. Tables are ready.');
        onTablesCreated?.(mergedFolder);
      } catch (err) {
        setStage('idle');
        const message = err instanceof Error ? err.message : 'Upload failed';
        setError(message);
        emitActivity(`Upload failed: ${message}`);
        await Promise.all(
          createdFileIds.map((id) => updateFileStatus(id, 'FAILED').catch(() => undefined)),
        );
      }
    },
    [emitActivity, uploadWithSocket],
  );

  return { upload, progress, stage, error };
}

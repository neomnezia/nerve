import { useState, useEffect, useRef } from 'react';
import { ArrowLeft, FilePlus, FileEdit, FileX, Loader2, RefreshCw } from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';
import { api } from '../../api/client';
import { DiffView } from './DiffView';
import { SelectionToolbar } from './SelectionToolbar';
import type { FileDiff, ModifiedFileSummary } from '../../types/chat';

// ------------------------------------------------------------------ //
//  File list view                                                      //
// ------------------------------------------------------------------ //

const STATUS_ICON: Record<string, typeof FileEdit> = {
  created: FilePlus,
  modified: FileEdit,
  deleted: FileX,
};

const STATUS_COLOR: Record<string, string> = {
  created: 'text-green-400',
  modified: 'text-amber-400',
  deleted: 'text-red-400',
};

const STATUS_BADGE: Record<string, string> = {
  created: '+',
  modified: 'M',
  deleted: 'D',
};

function splitPath(shortPath: string): { fileName: string; dirPath: string } {
  const parts = shortPath.split('/');
  const fileName = parts.pop() || shortPath;
  const dirPath = parts.join('/');
  return { fileName, dirPath };
}

function FileCard({ file, onClick }: { file: ModifiedFileSummary; onClick: () => void }) {
  const { fileName, dirPath } = splitPath(file.short_path);
  const Icon = STATUS_ICON[file.status] || FileEdit;
  const color = STATUS_COLOR[file.status] || 'text-[#888]';
  const badge = STATUS_BADGE[file.status] || '?';

  return (
    <button
      onClick={onClick}
      className="w-full text-left px-4 py-2.5 hover:bg-[#151515] transition-colors cursor-pointer border-b border-[#1a1a1a] last:border-b-0 group"
    >
      <div className="flex items-center gap-2.5">
        <span className={`text-[11px] font-bold font-mono w-4 text-center shrink-0 ${color}`}>
          {badge}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Icon size={13} className={`shrink-0 ${color}`} />
            <span className="text-[13px] font-medium text-[#ccc] truncate">{fileName}</span>
          </div>
          {dirPath && (
            <div className="text-[11px] text-[#555] truncate ml-[21px]">{dirPath}</div>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0 text-[11px] font-mono tabular-nums">
          {file.stats.additions > 0 && (
            <span className="text-green-400">+{file.stats.additions}</span>
          )}
          {file.stats.deletions > 0 && (
            <span className="text-red-400">&minus;{file.stats.deletions}</span>
          )}
        </div>
      </div>
    </button>
  );
}

// ------------------------------------------------------------------ //
//  Detail view (loads diff on demand)                                  //
// ------------------------------------------------------------------ //

function FileDetailView({ file, onBack }: { file: ModifiedFileSummary; onBack: () => void }) {
  const activeSession = useChatStore(s => s.activeSession);
  const [diff, setDiff] = useState<FileDiff | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.getFileDiff(activeSession, file.path)
      .then(data => { if (!cancelled) setDiff(data); })
      .catch(e => { if (!cancelled) setError(String(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [activeSession, file.path]);

  const { fileName } = splitPath(file.short_path);
  const color = STATUS_COLOR[file.status] || 'text-[#888]';

  return (
    <div className="flex flex-col h-full">
      {/* Detail header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[#222] bg-[#0a0a0a] shrink-0">
        <button
          onClick={onBack}
          className="w-5 h-5 flex items-center justify-center text-[#555] hover:text-[#999] cursor-pointer transition-colors"
        >
          <ArrowLeft size={14} />
        </button>
        <span className={`text-[13px] font-medium ${color}`}>{fileName}</span>
        <div className="flex items-center gap-1.5 text-[11px] font-mono tabular-nums">
          {diff?.stats && diff.stats.additions > 0 && (
            <span className="text-green-400">+{diff.stats.additions}</span>
          )}
          {diff?.stats && diff.stats.deletions > 0 && (
            <span className="text-red-400">&minus;{diff.stats.deletions}</span>
          )}
        </div>
      </div>
      <div className="text-[11px] text-[#555] px-4 py-1 bg-[#0a0a0a] border-b border-[#1a1a1a]">
        {file.short_path}
      </div>

      {/* Diff content */}
      <div ref={containerRef} className="flex-1 overflow-y-auto relative" data-role="plan">
        <SelectionToolbar containerRef={containerRef} />
        {loading && (
          <div className="flex items-center gap-2 justify-center py-8 text-[13px] text-[#555]">
            <Loader2 size={14} className="animate-spin" /> Loading diff...
          </div>
        )}
        {error && (
          <div className="px-4 py-4 text-[13px] text-red-400">Failed to load diff: {error}</div>
        )}
        {diff && !loading && <DiffView diff={diff} />}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ //
//  Main panel component                                                //
// ------------------------------------------------------------------ //

export function FileChangesPanel() {
  const modifiedFiles = useChatStore(s => s.modifiedFiles);
  const activeSession = useChatStore(s => s.activeSession);
  const fetchModifiedFiles = useChatStore(s => s.fetchModifiedFiles);
  const [selectedFile, setSelectedFile] = useState<ModifiedFileSummary | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Reset selection when session changes
  useEffect(() => {
    setSelectedFile(null);
  }, [activeSession]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchModifiedFiles(activeSession);
    setRefreshing(false);
  };

  if (selectedFile) {
    return (
      <FileDetailView
        file={selectedFile}
        onBack={() => setSelectedFile(null)}
      />
    );
  }

  const totalAdd = modifiedFiles.reduce((sum, f) => sum + f.stats.additions, 0);
  const totalDel = modifiedFiles.reduce((sum, f) => sum + f.stats.deletions, 0);

  return (
    <div className="flex flex-col h-full">
      {/* List header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#222] bg-[#0a0a0a] shrink-0">
        <div className="flex items-center gap-2 text-[12px] text-[#888]">
          <span>{modifiedFiles.length} file{modifiedFiles.length !== 1 ? 's' : ''}</span>
          {totalAdd > 0 && <span className="text-green-400 font-mono">+{totalAdd}</span>}
          {totalDel > 0 && <span className="text-red-400 font-mono">&minus;{totalDel}</span>}
        </div>
        <button
          onClick={handleRefresh}
          className="w-5 h-5 flex items-center justify-center text-[#444] hover:text-[#888] cursor-pointer transition-colors"
          title="Refresh file list"
        >
          <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* File list */}
      <div className="flex-1 overflow-y-auto">
        {modifiedFiles.length === 0 ? (
          <div className="px-4 py-8 text-center text-[13px] text-[#444]">
            No files modified in this session
          </div>
        ) : (
          modifiedFiles.map(file => (
            <FileCard
              key={file.path}
              file={file}
              onClick={() => setSelectedFile(file)}
            />
          ))
        )}
      </div>
    </div>
  );
}

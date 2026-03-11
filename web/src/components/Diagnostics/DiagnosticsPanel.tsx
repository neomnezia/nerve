import { useEffect, useState } from 'react';
import { api } from '../../api/client';

interface SourceStatus {
  cursor: string | null;
  last_run: string | null;
  records_fetched: number;
  records_processed: number;
  error: string | null;
}

export function DiagnosticsPanel() {
  const [data, setData] = useState<any>(null);
  const [cronLogs, setCronLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const [diag, logs] = await Promise.all([
          api.getDiagnostics(),
          api.getCronLogs(undefined, 20),
        ]);
        setData(diag);
        setCronLogs(logs.logs);
      } catch (e) {
        console.error('Failed to load diagnostics:', e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) return <div className="p-4 text-[#555]">Loading...</div>;
  if (!data) return <div className="p-4 text-red-400">Failed to load diagnostics</div>;

  const syncEntries = Object.entries(data.sync || {}) as [string, SourceStatus | string][];

  return (
    <div className="p-4 space-y-6 overflow-y-auto">
      {/* System */}
      <section>
        <h3 className="text-sm font-medium text-[#888] mb-2">System</h3>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="p-2 bg-[#1a1a1a] rounded">
            <div className="text-xs text-[#666]">Hostname</div>
            <div>{data.system?.hostname}</div>
          </div>
          <div className="p-2 bg-[#1a1a1a] rounded">
            <div className="text-xs text-[#666]">Platform</div>
            <div className="text-xs">{data.system?.platform}</div>
          </div>
          <div className="p-2 bg-[#1a1a1a] rounded">
            <div className="text-xs text-[#666]">Memory (RSS)</div>
            <div>{data.system?.memory_mb} MB</div>
          </div>
          <div className="p-2 bg-[#1a1a1a] rounded">
            <div className="text-xs text-[#666]">Disk Free</div>
            <div>{data.system?.disk_free_gb} / {data.system?.disk_total_gb} GB</div>
          </div>
        </div>
      </section>

      {/* Sources */}
      <section>
        <h3 className="text-sm font-medium text-[#888] mb-2">Sources</h3>
        {syncEntries.length === 0 ? (
          <div className="text-[#555] text-sm">No sources configured</div>
        ) : (
          <div className="space-y-1">
            {syncEntries.map(([source, info]) => {
              // Handle both old format (string cursor) and new format (object)
              const isObj = typeof info === 'object' && info !== null;
              const status = isObj ? info as SourceStatus : null;
              const hasError = status?.error;
              const lastRun = status?.last_run;
              const processed = status?.records_processed ?? 0;
              const fetched = status?.records_fetched ?? 0;

              return (
                <div key={source} className="p-2 bg-[#1a1a1a] rounded text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{source}</span>
                    {hasError ? (
                      <span className="text-xs text-red-400">error</span>
                    ) : lastRun ? (
                      <span className="text-xs text-green-400">{processed}/{fetched} records</span>
                    ) : (
                      <span className="text-xs text-[#666]">never run</span>
                    )}
                  </div>
                  {lastRun && (
                    <div className="text-xs text-[#555] mt-1">
                      Last: {new Date(lastRun).toLocaleString()}
                    </div>
                  )}
                  {hasError && (
                    <div className="text-xs text-red-400 mt-1">{status!.error}</div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Tasks / FTS */}
      {data.tasks && (
        <section>
          <h3 className="text-sm font-medium text-[#888] mb-2">Tasks / FTS Index</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="p-2 bg-[#1a1a1a] rounded">
              <div className="text-xs text-[#666]">Active</div>
              <div>{data.tasks.active}</div>
            </div>
            <div className="p-2 bg-[#1a1a1a] rounded">
              <div className="text-xs text-[#666]">Done</div>
              <div>{data.tasks.done}</div>
            </div>
            <div className="p-2 bg-[#1a1a1a] rounded">
              <div className="text-xs text-[#666]">FTS Indexed</div>
              <div>{data.tasks.fts_indexed} / {data.tasks.total}</div>
            </div>
            <div className="p-2 bg-[#1a1a1a] rounded">
              <div className="text-xs text-[#666]">FTS Status</div>
              <div className={data.tasks.fts_ok ? 'text-green-400' : 'text-red-400'}>
                {data.tasks.fts_ok ? '✓ in sync' : '✗ mismatch'}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Cron Logs */}
      <section>
        <h3 className="text-sm font-medium text-[#888] mb-2">Recent Cron Logs</h3>
        {cronLogs.length === 0 ? (
          <div className="text-[#555] text-sm">No cron logs yet</div>
        ) : (
          <div className="space-y-1">
            {cronLogs.map((log) => (
              <div key={log.id} className="p-2 bg-[#1a1a1a] rounded text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{log.job_id}</span>
                  <span className={`text-xs ${log.status === 'success' ? 'text-green-400' : 'text-red-400'}`}>
                    {log.status}
                  </span>
                </div>
                <div className="text-xs text-[#666] mt-1">{log.started_at}</div>
                {log.error && <div className="text-xs text-red-400 mt-1">{log.error}</div>}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Info */}
      <section>
        <div className="text-xs text-[#555]">
          Workspace: {data.workspace} | Sessions: {data.sessions_count}
        </div>
      </section>
    </div>
  );
}

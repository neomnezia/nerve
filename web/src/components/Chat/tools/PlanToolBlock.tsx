import { useState } from 'react';
import { ChevronRight, ChevronDown, Lightbulb, ListTodo, Loader2, ExternalLink } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { ToolCallBlockData } from '../../../types/chat';

/** Extract readable text from MCP content blocks. */
function extractText(result: string): string {
  try {
    const parsed = JSON.parse(result);
    if (Array.isArray(parsed)) {
      return parsed
        .filter((b: any) => b.type === 'text')
        .map((b: any) => b.text)
        .join('\n');
    }
  } catch { /* not JSON */ }
  return result;
}

interface ParsedPlan {
  status: string;
  taskTitle: string;
  planId: string;
  version: string;
  date: string;
}

/** Parse plan list lines: "- [status] title — plan plan-xxx vN (date)" */
function parsePlanList(text: string): ParsedPlan[] {
  const items: ParsedPlan[] = [];
  for (const line of text.split('\n')) {
    const match = line.match(/^-\s*\[(\w+)\]\s*(.+?)\s*—\s*plan\s+(plan-\S+)\s+v(\d+)\s*\(([^)]+)\)/);
    if (match) {
      items.push({
        status: match[1],
        taskTitle: match[2].trim(),
        planId: match[3],
        version: match[4],
        date: match[5],
      });
    }
  }
  return items;
}

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-500/15 text-yellow-400',
  approved: 'bg-green-500/15 text-green-400',
  implementing: 'bg-blue-500/15 text-blue-400',
  declined: 'bg-red-500/15 text-red-400',
  superseded: 'bg-[#333] text-[#888]',
};

export function PlanToolBlock({ block }: { block: ToolCallBlockData }) {
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();
  const isRunning = block.status === 'running';

  const toolName = block.tool.split('__').pop() || block.tool;
  const isPropose = toolName === 'plan_propose';
  const isList = toolName === 'plan_list';

  const label = isPropose ? 'Propose Plan' : 'List Plans';
  const Icon = isPropose ? Lightbulb : ListTodo;

  const taskId = String(block.input.task_id || '');
  const resultText = block.result ? extractText(block.result) : '';
  const planList = isList ? parsePlanList(resultText) : [];

  // Extract plan ID from result for propose
  const planIdMatch = isPropose ? resultText.match(/Plan proposed:\s*(plan-\S+)/) : null;
  const proposedPlanId = planIdMatch?.[1];

  return (
    <div className="my-1.5 border border-amber-500/20 rounded-lg bg-[#141411] overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-3 py-2 text-left cursor-pointer hover:bg-[#1a1a18] transition-colors"
      >
        {isRunning
          ? <Loader2 size={14} className="text-amber-400 animate-spin shrink-0" />
          : <Icon size={14} className={`shrink-0 ${block.isError ? 'text-red-400' : 'text-amber-400'}`} />
        }
        <span className="text-[13px] font-medium text-amber-300">{label}</span>
        {isPropose && taskId && <span className="text-[12px] text-[#666] truncate">{taskId}</span>}
        {isList && planList.length > 0 && (
          <span className="text-[10px] text-amber-400/60 shrink-0">{planList.length} plans</span>
        )}
        <div className="ml-auto shrink-0">
          {expanded ? <ChevronDown size={14} className="text-[#555]" /> : <ChevronRight size={14} className="text-[#555]" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-amber-500/10">
          {/* Propose: show what was proposed */}
          {isPropose && (
            <div className="px-3 py-2">
              {block.input.content ? (
                <div className="text-[12px] text-[#999] max-h-40 overflow-y-auto whitespace-pre-wrap">
                  {String(block.input.content).slice(0, 500)}
                  {String(block.input.content).length > 500 ? '...' : null}
                </div>
              ) : null}
              {proposedPlanId && !block.isError && (
                <button
                  onClick={(e) => { e.stopPropagation(); navigate(`/plans/${proposedPlanId}`); }}
                  className="mt-2 flex items-center gap-1 text-[11px] text-amber-400 hover:text-amber-300 cursor-pointer"
                >
                  <ExternalLink size={10} /> Review plan
                </button>
              )}
            </div>
          )}

          {/* Plan list */}
          {planList.length > 0 ? (
            <div className="px-3 py-2 space-y-1 max-h-60 overflow-y-auto">
              {planList.map((p, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 text-[12px] cursor-pointer hover:bg-[#1f1f1c] rounded px-1 py-0.5"
                  onClick={() => navigate(`/plans/${p.planId}`)}
                >
                  <span className={`px-1.5 py-0.5 rounded text-[10px] shrink-0 ${STATUS_COLORS[p.status] || 'bg-[#333] text-[#888]'}`}>
                    {p.status}
                  </span>
                  <span className="text-[#bbb] truncate">{p.taskTitle}</span>
                  <span className="text-[10px] text-[#555] shrink-0">v{p.version}</span>
                </div>
              ))}
            </div>
          ) : resultText && !isPropose ? (
            <pre className={`px-3 py-2 text-[12px] whitespace-pre-wrap max-h-60 overflow-y-auto ${block.isError ? 'text-red-400' : 'text-[#999]'}`}>
              {resultText}
            </pre>
          ) : null}

          {/* Success for propose */}
          {isPropose && resultText && !block.isError && (
            <div className="px-3 py-1.5 text-[11px] text-green-400/70 border-t border-amber-500/10">
              Plan proposed — awaiting review
            </div>
          )}

          {block.isError && resultText && (
            <pre className="px-3 py-2 text-[12px] text-red-400 whitespace-pre-wrap border-t border-amber-500/10">
              {resultText}
            </pre>
          )}

          {isRunning && block.result === undefined && (
            <div className="px-3 py-3 text-[12px] text-[#666] flex items-center gap-2">
              <Loader2 size={12} className="animate-spin" /> {isPropose ? 'Proposing...' : 'Loading...'}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

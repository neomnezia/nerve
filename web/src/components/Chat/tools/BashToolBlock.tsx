import { useState } from 'react';
import { ChevronRight, ChevronDown, Terminal, Loader2 } from 'lucide-react';
import type { ToolCallBlockData } from '../../../types/chat';

export function BashToolBlock({ block }: { block: ToolCallBlockData }) {
  const [expanded, setExpanded] = useState(false);
  const isRunning = block.status === 'running';
  const command = String(block.input.command || '');
  const truncatedCmd = command.length > 80 ? command.slice(0, 80) + '...' : command;

  return (
    <div className="my-1.5 border border-[#2a2a2a] rounded-lg bg-[#0a0a0a] overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-3 py-2 text-left cursor-pointer hover:bg-[#111] transition-colors"
      >
        {isRunning
          ? <Loader2 size={14} className="text-[#6366f1] animate-spin shrink-0" />
          : <Terminal size={14} className={`shrink-0 ${block.isError ? 'text-red-400' : 'text-emerald-400'}`} />
        }
        <span className="text-emerald-500 text-[13px] font-mono select-none">$</span>
        <span className="text-[13px] font-mono text-[#ccc] truncate">{truncatedCmd}</span>
        <div className="ml-auto shrink-0">
          {expanded ? <ChevronDown size={14} className="text-[#555]" /> : <ChevronRight size={14} className="text-[#555]" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-[#1a1a1a]">
          {/* Full command */}
          {command.length > 80 && (
            <div className="px-3 py-2 border-b border-[#1a1a1a]">
              <pre className="text-[12px] font-mono text-[#ccc] whitespace-pre-wrap">{command}</pre>
            </div>
          )}

          {/* Output */}
          {block.result !== undefined && (
            <pre className={`px-3 py-2 text-[12px] font-mono whitespace-pre-wrap max-h-80 overflow-y-auto ${block.isError ? 'text-red-400' : 'text-[#888]'}`}>
              {block.result}
            </pre>
          )}

          {isRunning && block.result === undefined && (
            <div className="px-3 py-3 text-[12px] text-[#666] flex items-center gap-2">
              <Loader2 size={12} className="animate-spin" /> Running...
            </div>
          )}
        </div>
      )}
    </div>
  );
}

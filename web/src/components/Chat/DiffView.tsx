import { Fragment } from 'react';
import type { FileDiff, DiffHunk, DiffLine as DiffLineType } from '../../types/chat';

// ------------------------------------------------------------------ //
//  Hunk header — @@ -old,count +new,count @@ context                  //
// ------------------------------------------------------------------ //

function HunkHeader({ hunk }: { hunk: DiffHunk }) {
  return (
    <div className="bg-[#161625] text-[11px] px-3 py-1 border-y border-[#222240] select-none flex items-center gap-2 sticky top-0 z-[1]">
      <span className="text-indigo-400 font-mono">
        @@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@
      </span>
      {hunk.header && (
        <span className="text-[#555] truncate">{hunk.header}</span>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ //
//  Diff line — single line with gutters                                //
// ------------------------------------------------------------------ //

const LINE_STYLES: Record<string, string> = {
  addition: 'bg-green-950/25',
  deletion: 'bg-red-950/25',
  context: '',
  info: '',
};

const TEXT_STYLES: Record<string, string> = {
  addition: 'text-green-300/90',
  deletion: 'text-red-300/90',
  context: 'text-[#888]',
  info: 'text-[#555] italic',
};

const PREFIX: Record<string, string> = {
  addition: '+',
  deletion: '\u2212',  // minus sign
  context: ' ',
  info: '',
};

const GUTTER_STYLES: Record<string, string> = {
  addition: 'bg-green-950/15 border-green-900/30',
  deletion: 'bg-red-950/15 border-red-900/30',
  context: 'border-[#1a1a1a]',
  info: 'border-[#1a1a1a]',
};

function DiffLine({ line }: { line: DiffLineType }) {
  const bg = LINE_STYLES[line.type] || '';
  const text = TEXT_STYLES[line.type] || 'text-[#888]';
  const prefix = PREFIX[line.type] || '';
  const gutterBg = GUTTER_STYLES[line.type] || '';

  return (
    <div className={`flex ${bg} hover:brightness-125 transition-[filter] duration-75 group`}>
      {/* Old line number gutter */}
      <span
        className={`w-[48px] shrink-0 text-right pr-2 text-[10px] leading-[20px] text-[#444] select-none border-r ${gutterBg} font-mono`}
      >
        {line.old_line ?? ''}
      </span>
      {/* New line number gutter */}
      <span
        className={`w-[48px] shrink-0 text-right pr-2 text-[10px] leading-[20px] text-[#444] select-none border-r ${gutterBg} font-mono`}
      >
        {line.new_line ?? ''}
      </span>
      {/* Prefix (+/-/space) */}
      <span className={`w-[20px] shrink-0 text-center select-none text-[12px] leading-[20px] ${text}`}>
        {prefix}
      </span>
      {/* Content */}
      <span className={`text-[12px] leading-[20px] font-mono whitespace-pre flex-1 pr-4 ${text}`}>
        {line.content}
      </span>
    </div>
  );
}

// ------------------------------------------------------------------ //
//  Collapsed context between hunks                                     //
// ------------------------------------------------------------------ //

function CollapsedLines({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <div className="flex items-center justify-center py-1 text-[11px] text-[#444] bg-[#0f0f0f] border-y border-[#1a1a1a]">
      <span className="px-3">⋯ {count} unchanged line{count !== 1 ? 's' : ''} ⋯</span>
    </div>
  );
}

function prevHunkEnd(hunk: DiffHunk): number {
  return hunk.old_start + hunk.old_count;
}

// ------------------------------------------------------------------ //
//  Main DiffView component                                             //
// ------------------------------------------------------------------ //

export function DiffView({ diff }: { diff: FileDiff }) {
  if (diff.binary) {
    return (
      <div className="px-4 py-6 text-center text-[13px] text-[#555]">
        Binary file — diff not available
      </div>
    );
  }

  if (diff.status === 'unchanged' || diff.hunks.length === 0) {
    return (
      <div className="px-4 py-6 text-center text-[13px] text-[#555]">
        No changes
      </div>
    );
  }

  return (
    <div className="font-mono text-[12px] leading-[20px] overflow-x-auto">
      {diff.hunks.map((hunk, i) => (
        <Fragment key={i}>
          {/* Collapsed context between hunks */}
          {i > 0 && (
            <CollapsedLines count={hunk.old_start - prevHunkEnd(diff.hunks[i - 1])} />
          )}

          {/* Hunk header */}
          <HunkHeader hunk={hunk} />

          {/* Lines */}
          {hunk.lines.map((line, j) => (
            <DiffLine key={j} line={line} />
          ))}
        </Fragment>
      ))}

      {diff.truncated && (
        <div className="text-center py-3 text-[11px] text-[#555] bg-[#0f0f0f] border-t border-[#222]">
          Diff truncated at {2000} lines
        </div>
      )}
    </div>
  );
}

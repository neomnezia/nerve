import type { MessageBlock, ToolCallBlockData } from './chat';

/**
 * A group of consecutive tool_call blocks sharing the same `tool` name.
 * Only created when the run of consecutive same-tool calls has length >= 2.
 */
export interface ToolCallGroup {
  type: 'tool_call_group';
  tool: string;
  blocks: ToolCallBlockData[];
}

/**
 * Union type used by rendering components after grouping.
 */
export type RenderItem = MessageBlock | ToolCallGroup;

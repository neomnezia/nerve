import type { ChatMessage, MessageBlock } from '../types/chat';

export function hydrateMessage(raw: any): ChatMessage {
  if (raw.role === 'user') {
    return {
      id: raw.id,
      role: 'user',
      blocks: [{ type: 'text', content: raw.content || '' }],
      channel: raw.channel,
      created_at: raw.created_at,
    };
  }

  // If ordered blocks are stored, use them directly (preserves interleaving)
  if (raw.blocks && Array.isArray(raw.blocks)) {
    const blocks: MessageBlock[] = raw.blocks.map((b: any) => {
      if (b.type === 'thinking') {
        return { type: 'thinking' as const, content: b.content || '' };
      }
      if (b.type === 'tool_call') {
        return {
          type: 'tool_call' as const,
          toolUseId: b.tool_use_id || '',
          tool: b.tool,
          input: b.input || {},
          result: b.result,
          isError: b.is_error,
          status: 'complete' as const,
        };
      }
      // Default: text
      return { type: 'text' as const, content: b.content || '' };
    });

    return {
      id: raw.id,
      role: 'assistant',
      blocks,
      channel: raw.channel,
      created_at: raw.created_at,
    };
  }

  // Fallback for pre-migration messages without blocks column:
  // thinking → tool_calls → text (loses interleaving)
  const blocks: MessageBlock[] = [];

  if (raw.thinking) {
    blocks.push({ type: 'thinking', content: raw.thinking });
  }

  if (raw.tool_calls) {
    const toolCalls = typeof raw.tool_calls === 'string' ? JSON.parse(raw.tool_calls) : raw.tool_calls;
    for (const tc of toolCalls) {
      blocks.push({
        type: 'tool_call',
        toolUseId: tc.tool_use_id || '',
        tool: tc.tool,
        input: tc.input || {},
        result: tc.result,
        isError: tc.is_error,
        status: 'complete',
      });
    }
  }

  if (raw.content) {
    blocks.push({ type: 'text', content: raw.content });
  }

  return {
    id: raw.id,
    role: 'assistant',
    blocks,
    channel: raw.channel,
    created_at: raw.created_at,
  };
}

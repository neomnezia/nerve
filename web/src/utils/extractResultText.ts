/** Extract readable text from MCP content blocks (used by SubagentToolBlock and chatStore). */
export function extractResultText(result: string): string {
  try {
    const parsed = JSON.parse(result);
    if (Array.isArray(parsed)) {
      return parsed
        .filter((b: any) => b.type === 'text' && !b.text.startsWith('agentId:') && !b.text.startsWith('<usage>'))
        .map((b: any) => b.text)
        .join('\n');
    }
  } catch {
    // Not JSON
  }
  return result;
}

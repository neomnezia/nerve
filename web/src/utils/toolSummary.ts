export function getToolSummary(tool: string, input: Record<string, unknown>): string {
  const truncate = (s: string, max = 60) => s.length > max ? s.slice(0, max) + '...' : s;

  switch (tool) {
    case 'Read':
      return truncate(String(input.file_path || ''));
    case 'Write':
    case 'Edit':
      return truncate(String(input.file_path || ''));
    case 'Bash':
      return truncate(String(input.command || ''));
    case 'Grep':
      return truncate(String(input.pattern || ''));
    case 'Glob':
      return truncate(String(input.pattern || ''));
    case 'WebSearch':
      return truncate(String(input.query || ''));
    case 'WebFetch':
      return truncate(String(input.url || ''));
    default: break;
  }

  // MCP source tools
  if (tool.includes('list_sources')) {
    const consumer = String(input.consumer || '');
    return consumer ? `consumer="${consumer}"` : '';
  }
  if (tool.includes('poll_all')) {
    return `consumer="${String(input.consumer || '')}"`;
  }
  if (tool.includes('poll_source')) {
    const source = String(input.source || '');
    const consumer = String(input.consumer || '');
    return source ? `${source} (${consumer})` : consumer;
  }
  if (tool.includes('read_source')) {
    return truncate(String(input.source || ''));
  }

  // For MCP tools, show the first string value
  for (const val of Object.values(input)) {
    if (typeof val === 'string' && val.length > 0) {
      return truncate(val);
    }
  }
  return '';
}

/**
 * Assign a human-readable group label based on when something was last updated.
 *
 * Today     → "Last hour" / "N hours ago"
 * Yesterday → "Yesterday"
 * This week → Day name (Monday, Tuesday, …)
 * Older     → "Last 30 Days" or "February 2026" etc.
 *
 * Items arrive sorted by updated_at DESC, so Map insertion order
 * naturally produces the correct top-to-bottom group sequence.
 */
export function getDateGroup(updatedAt: string): string {
  const now = new Date();
  const date = new Date(updatedAt.includes('T') ? updatedAt : updatedAt.replace(' ', 'T') + 'Z');

  const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterdayStart = new Date(todayStart.getTime() - 86400000);

  // Today — hourly buckets
  if (date >= todayStart) {
    const hoursAgo = Math.floor((now.getTime() - date.getTime()) / 3600000);
    if (hoursAgo < 1) return 'Last hour';
    if (hoursAgo === 1) return '1 hour ago';
    return `${hoursAgo} hours ago`;
  }

  if (date >= yesterdayStart) return 'Yesterday';

  // This week — individual day names
  const daysDiff = Math.floor((todayStart.getTime() - date.getTime()) / 86400000);
  if (daysDiff < 7) {
    return date.toLocaleDateString(undefined, { weekday: 'long' });
  }

  // Recent — last 30 days
  if (daysDiff < 30) return 'Last 30 Days';

  // Older — month + year
  return date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
}

/**
 * Group items by date label. Preserves the order items arrive in
 * (most-recent-first from the API), so groups appear top-to-bottom
 * from newest to oldest without needing a hardcoded order list.
 */
export function groupByDate<T extends { updated_at: string }>(
  items: T[],
): { group: string; items: T[] }[] {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const group = getDateGroup(item.updated_at);
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group)!.push(item);
  }
  return Array.from(groups.entries()).map(([group, groupItems]) => ({
    group,
    items: groupItems,
  }));
}

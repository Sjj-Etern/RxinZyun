type DateValue = string | number | Date | null | undefined;

const pad2 = (value: number) => String(value).padStart(2, '0');

export function formatDateTime(value: DateValue) {
  if (!value) return '-';

  if (typeof value === 'string') {
    const plain = value.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})[T\s](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?/);
    const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value.trim());

    if (plain && !hasTimezone) {
      const [, y, m, d, h, min, s = '0'] = plain;
      return `${y}-${pad2(Number(m))}-${pad2(Number(d))} ${pad2(Number(h))}:${pad2(Number(min))}:${pad2(Number(s))}`;
    }
  }

  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);

  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
}

export function formatBeijingDateTime(value: DateValue) {
  if (!value) return '-';

  const normalized = typeof value === 'string'
    && /^(\d{4})[-/](\d{1,2})[-/](\d{1,2})[T\s](\d{1,2}):(\d{1,2})(?::(\d{1,2}))?/.test(value)
    && !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value.trim())
    ? `${value.trim().replace(' ', 'T')}Z`
    : value;
  const date = normalized instanceof Date ? normalized : new Date(normalized);
  if (Number.isNaN(date.getTime())) return String(value);

  const beijing = new Date(date.getTime() + 8 * 60 * 60 * 1000);
  return `${beijing.getUTCFullYear()}-${pad2(beijing.getUTCMonth() + 1)}-${pad2(beijing.getUTCDate())} ${pad2(beijing.getUTCHours())}:${pad2(beijing.getUTCMinutes())}:${pad2(beijing.getUTCSeconds())}`;
}

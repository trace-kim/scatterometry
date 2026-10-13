// Client-side file downloads (CSV tables, project JSON).

export function downloadText(text: string, fileName: string, type = "text/csv;charset=utf-8") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function cell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = typeof value === "number" ? (Number.isFinite(value) ? String(value) : "") : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv<T extends object>(rows: T[], columns?: (keyof T & string)[]): string {
  const keys = columns ?? (rows.length ? (Object.keys(rows[0]) as (keyof T & string)[]) : []);
  return [keys.join(","), ...rows.map((row) => keys.map((k) => cell(row[k])).join(","))].join("\n");
}

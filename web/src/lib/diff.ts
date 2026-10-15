// Parse the unified diff that autofix stores in report.diff.

export type DiffLineKind = 'file' | 'hunk' | 'add' | 'del' | 'ctx';

export interface DiffLine {
  kind: DiffLineKind;
  text: string;
}

export interface DiffFile {
  path: string;
  added: number;
  removed: number;
}

export interface ParsedDiff {
  files: DiffFile[];
  lines: DiffLine[];
  added: number;
  removed: number;
}

const NOISE = /^(index |--- |\+\+\+ |new file|deleted file|old mode|new mode|similarity|rename |Binary files)/;

export function parseDiff(text: string | null | undefined): ParsedDiff {
  const out: ParsedDiff = { files: [], lines: [], added: 0, removed: 0 };
  if (!text) return out;

  let current: DiffFile | null = null;

  for (const raw of String(text).split('\n')) {
    if (raw.startsWith('diff --git')) {
      const match = raw.match(/ b\/(.+)$/);
      current = { path: match ? match[1] : raw.replace('diff --git ', ''), added: 0, removed: 0 };
      out.files.push(current);
      out.lines.push({ kind: 'file', text: current.path });
      continue;
    }

    if (NOISE.test(raw)) continue;

    if (raw.startsWith('@@')) {
      // "@@ -12,7 +12,7 @@ def start_requests(self):" -> keep the context tail,
      // which is what the design shows.
      const tail = raw.replace(/^@@[^@]*@@\s?/, '');
      out.lines.push({ kind: 'hunk', text: tail ? `@@ ${tail}` : raw });
      continue;
    }

    if (raw.startsWith('+')) {
      out.added += 1;
      if (current) current.added += 1;
      out.lines.push({ kind: 'add', text: raw });
      continue;
    }

    if (raw.startsWith('-')) {
      out.removed += 1;
      if (current) current.removed += 1;
      out.lines.push({ kind: 'del', text: raw });
      continue;
    }

    if (raw === '\\ No newline at end of file') continue;
    if (raw === '' && out.lines.length === 0) continue;

    out.lines.push({ kind: 'ctx', text: raw });
  }

  while (out.lines.length > 0) {
    const last = out.lines[out.lines.length - 1];
    if (last.kind === 'ctx' && last.text.trim() === '') out.lines.pop();
    else break;
  }

  return out;
}

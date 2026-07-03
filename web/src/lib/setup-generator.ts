// Shared generator logic for the setup wizard (/setup and /en/setup).
//
// Extracted (S-248) so the two locale pages stop carrying pasted copies of
// the YAML / launch-command / ZIP generation. Locale-dependent lines are
// injected by each page via `LaunchStrings`; everything else the wizard
// emits is locale-independent by design (the generated YAML is English).
//
// The emitted `version:` / `methodology:` lines bake VERSION in at build
// time (lib/version.ts reads plugin/.claude-plugin/plugin.json, and the
// site is rebuilt on every release — release-checklist step 6). This
// replaces the pattern-stamping scripts/bump_version.py used to do on
// both setup pages, so no version literal lives in this file or in the
// pages that import it.
import { VERSION } from './version';

export interface WizardMember {
  email: string;
  name: string;
  id: string;
  role: string;
  fte: number;
  capacity: number;
  contract: string;
}

/** Locale-specific lines injected into the Path A/B/C launch snippets. */
export interface LaunchStrings {
  /** Comment shown before `/edpa:setup` in Paths A + B (plugin install hint). */
  installComment: string;
  /** The `/edpa:setup` line with a localized trailing comment (Path B). */
  interactiveSetup: string;
  /** Comment describing what install.sh vendors (Path C). */
  vendorComment: string;
  /** Comment pointing back to Claude Code after install.sh (Path C). */
  thenComment: string;
}

function isoToday(): string {
  return new Date().toISOString().split('T')[0];
}

export function generatePeopleYaml(members: WizardMember[]): string {
  const lines = ['# EDPA People Registry', `# Generated: ${isoToday()}`, '', 'people:'];
  members.forEach(m => {
    if (!m.email && !m.name) return;
    lines.push(`  - name: "${m.name}"`);
    lines.push(`    id: "${m.id}"`);
    lines.push(`    email: "${m.email}"`);
    lines.push(`    role: ${m.role}`);
    lines.push(`    fte: ${m.fte}`);
    lines.push(`    capacity_h: ${m.capacity}`);
    if (m.contract) {
      lines.push(`    contract: ${m.contract}`);
    }
    lines.push('');
  });
  const totalFte = members.reduce((s, m) => s + m.fte, 0);
  const totalCap = members.reduce((s, m) => s + m.capacity, 0);
  lines.push(`# Total: ${members.filter(m => m.email || m.name).length} members, ${totalFte.toFixed(1)} FTE, ${totalCap}h/iteration`);
  return lines.join('\n');
}

export function generateConfigYaml(opts: { githubOrg: string; githubRepo: string }): string {
  const org = opts.githubOrg || 'my-org';
  const repo = opts.githubRepo || 'my-project';
  const lines = [
    '# EDPA Configuration',
    `# Generated: ${isoToday()}`,
    '',
    'edpa:',
    `  version: "${VERSION}"`,
    '',
    '# Optional: GitHub repo for contribution-sync (--with-ci). Local-first;',
    '# omit this block if you are not using the PR-signal CI workflow.',
    'github:',
    `  org: "${org}"`,
    `  repo: "${repo}"`,
    '',
    'scoring:',
    '  contribution_weights:',
    '    commit: 0.25',
    '    contribute_command: 0.6',
    '    pr_reviewer: 0.25',
    '    comment: 0.15',
    '',
    'outputs:',
    '  snapshots_dir: "snapshots"',
    '  reports_dir: "reports"',
    '  signed_dir: "signed"',
  ];
  return lines.join('\n');
}

export function generateProjectYaml(opts: { projectName: string; program: string }): string {
  const name = opts.projectName || 'My Project';
  const program = opts.program;
  const lines = [
    '# EDPA Project Configuration (.edpa/config/edpa.yaml)',
    `# Generated: ${isoToday()}`,
    '',
    'project:',
    `  name: "${name}"`,
    '  description: ""',
  ];
  if (program) {
    lines.push('  funding:');
    lines.push(`    program: "${program}"`);
    lines.push('    registration: ""');
  }
  lines.push('  organizations:');
  lines.push('    - name: ""');
  lines.push('      legal_name: ""');
  lines.push('      role: "primary"');
  lines.push('      tax_id: ""');
  lines.push('      vat_id: ""');
  lines.push('');
  lines.push('governance:');
  lines.push(`  methodology: "EDPA ${VERSION}"`);
  return lines.join('\n');
}

export function generateLaunchCommands(
  githubRepo: string,
  strings: LaunchStrings,
): { a: string; b: string; c: string } {
  const repo = githubRepo || '{repo}';
  return {
    a: [
      `cd ${repo}`,
      strings.installComment,
      `/edpa:setup --with-ci --with-hooks --with-rules`,
    ].join('\n'),
    b: [
      `cd ${repo}`,
      strings.installComment,
      strings.interactiveSetup,
    ].join('\n'),
    c: [
      `cd ${repo}`,
      `curl -fsSL https://edpa.technomaton.com/install.sh | sh`,
      strings.vendorComment,
      strings.thenComment,
    ].join('\n'),
  };
}

/** Build a stored (uncompressed) ZIP archive of the generated config files. */
export function buildZipBlob(files: Array<{ name: string; content: string }>): Blob {
  const encoder = new TextEncoder();
  const parts: Uint8Array[] = [];
  const centralDir: Uint8Array[] = [];
  let offset = 0;

  for (const file of files) {
    const nameBytes = encoder.encode(file.name);
    const contentBytes = encoder.encode(file.content);

    const localHeader = new Uint8Array(30 + nameBytes.length);
    const lv = new DataView(localHeader.buffer);
    lv.setUint32(0, 0x04034b50, true);
    lv.setUint16(4, 20, true);
    lv.setUint16(6, 0, true);
    lv.setUint16(8, 0, true);
    lv.setUint16(10, 0, true);
    lv.setUint16(12, 0, true);
    lv.setUint32(14, crc32(contentBytes), true);
    lv.setUint32(18, contentBytes.length, true);
    lv.setUint32(22, contentBytes.length, true);
    lv.setUint16(26, nameBytes.length, true);
    lv.setUint16(28, 0, true);
    localHeader.set(nameBytes, 30);

    const cdEntry = new Uint8Array(46 + nameBytes.length);
    const cv = new DataView(cdEntry.buffer);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(4, 20, true);
    cv.setUint16(6, 20, true);
    cv.setUint16(8, 0, true);
    cv.setUint16(10, 0, true);
    cv.setUint16(12, 0, true);
    cv.setUint16(14, 0, true);
    cv.setUint32(16, crc32(contentBytes), true);
    cv.setUint32(20, contentBytes.length, true);
    cv.setUint32(24, contentBytes.length, true);
    cv.setUint16(28, nameBytes.length, true);
    cv.setUint16(30, 0, true);
    cv.setUint16(32, 0, true);
    cv.setUint16(34, 0, true);
    cv.setUint16(36, 0, true);
    cv.setUint32(38, 0, true);
    cv.setUint32(42, offset, true);
    cdEntry.set(nameBytes, 46);

    parts.push(localHeader, contentBytes);
    centralDir.push(cdEntry);
    offset += localHeader.length + contentBytes.length;
  }

  const cdOffset = offset;
  let cdSize = 0;
  centralDir.forEach(e => cdSize += e.length);

  const eocd = new Uint8Array(22);
  const ev = new DataView(eocd.buffer);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(4, 0, true);
  ev.setUint16(6, 0, true);
  ev.setUint16(8, files.length, true);
  ev.setUint16(10, files.length, true);
  ev.setUint32(12, cdSize, true);
  ev.setUint32(16, cdOffset, true);
  ev.setUint16(20, 0, true);

  return new Blob([...parts, ...centralDir, eocd], { type: 'application/zip' });
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xFFFFFFFF;
  for (let i = 0; i < bytes.length; i++) {
    crc ^= bytes[i];
    for (let j = 0; j < 8; j++) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xEDB88320 : 0);
    }
  }
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

/**
 * Plain-text formatters for the inline-flow REPL.
 *
 * The chat REPL writes already-committed turns and the welcome banner
 * directly to ``stdout`` so the terminal's native scrollback owns
 * history. ink only redraws the dynamic strip at the bottom (input +
 * status + any in-flight picker/modal). These formatters produce ANSI
 * strings the REPL feeds into ``console.log``.
 *
 * Visual fidelity vs ink components:
 *
 *  - Turn rendering matches the ink Turn component closely (same
 *    glyphs, same role-keyed layout, no markdown re-render — already-
 *    committed turns don't reflow on resize, so a single render at
 *    print time is enough).
 *  - Welcome rendering is intentionally simpler than the ink card —
 *    no border box, no flex columns, just a few labeled lines. The
 *    card visual loses fidelity here in exchange for not needing a
 *    React-tree-to-string layout engine.
 */
import type { Turn, ToolCall, TurnBlock } from '../components/Turn.js';
import type { WelcomeStats } from '../components/Welcome.js';

const RESET = '\x1b[0m';
const DIM = '\x1b[2m';
const ITALIC = '\x1b[3m';
const BOLD = '\x1b[1m';

const FG_GREEN = '\x1b[32m';
const FG_RED = '\x1b[31m';
const FG_GRAY = '\x1b[90m';
const FG_ORANGE = '\x1b[38;5;208m';   // 256-color ≈ OpenProgram primary
const BG_USER = '\x1b[48;5;225m';     // pale pink (matches user.bg in light theme)
const FG_USER = '\x1b[38;5;52m';      // dark red text on the pale pink

const TRUNC = 80;

const truncate = (s: string, n = TRUNC): string =>
  s.length > n ? s.slice(0, n - 1) + '…' : s;

const wrapLines = (text: string): string[] =>
  text.split('\n');

const formatToolCall = (call: ToolCall): string[] => {
  const arrow =
    call.status === 'running' ? '◌'
    : call.status === 'error' ? '✗'
    : '●';
  const arrowColor =
    call.status === 'running' ? FG_GRAY
    : call.status === 'error' ? FG_RED
    : FG_GREEN;
  const head =
    `  ${arrowColor}${arrow}${RESET} ${BOLD}${call.tool}${RESET}` +
    (call.input ? `${FG_GRAY} · ${truncate(call.input.split('\n')[0] ?? '')}${RESET}` : '');
  const out = [head];
  if (call.result) {
    const firstLine = call.result.split('\n')[0] ?? '';
    const moreLines = call.result.split('\n').length - 1;
    const suffix = moreLines > 0 ? `  (+${moreLines} lines)` : '';
    out.push(`    ${FG_GRAY}└ ${truncate(firstLine)}${suffix}${RESET}`);
  }
  return out;
};

const formatUserTurn = (turn: Turn): string => {
  const lines = wrapLines(turn.text);
  const out: string[] = [];
  for (let i = 0; i < lines.length; i++) {
    const prefix = i === 0 ? '> ' : '  ';
    const body = lines[i] || ' ';
    out.push(`${BG_USER}${FG_USER} ${prefix}${body} ${RESET}`);
  }
  out.push('');   // blank trailing line — visually separates turns
  return out.join('\n');
};

const formatAssistantTurn = (turn: Turn): string => {
  const blocks: TurnBlock[] =
    turn.blocks && turn.blocks.length > 0
      ? turn.blocks
      : [
          ...(turn.text ? [{ kind: 'text' as const, text: turn.text }] : []),
          ...((turn.tools ?? []).map((t) => ({ kind: 'tool' as const, call: t }))),
        ];

  const firstTextIndex = blocks.findIndex((b) => b.kind === 'text');
  const out: string[] = [];

  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    if (!b) continue;
    if (b.kind === 'tool') {
      for (const line of formatToolCall(b.call)) out.push(line);
      continue;
    }
    const lines = wrapLines(b.text);
    for (let j = 0; j < lines.length; j++) {
      const isFirstLine = i === firstTextIndex && j === 0;
      const prefix = isFirstLine ? `${FG_GREEN}● ${RESET}` : '  ';
      out.push(`${prefix}${lines[j] || ' '}`);
    }
  }
  out.push('');
  return out.join('\n');
};

const formatSystemTurn = (turn: Turn): string => {
  const lines = wrapLines(turn.text);
  const styled = lines.map((l) => `${FG_GRAY}${ITALIC} ${l || ' '}${RESET}`);
  styled.push('');
  return styled.join('\n');
};

/**
 * Render a single committed turn to an ANSI string suitable for
 * ``console.log`` / ``process.stdout.write``. One trailing blank
 * line is included so consecutive turns are visually separated.
 */
export function formatTurnText(turn: Turn): string {
  if (turn.role === 'user') return formatUserTurn(turn);
  if (turn.role === 'assistant') return formatAssistantTurn(turn);
  return formatSystemTurn(turn);
}

// ──────────────────────────────────────────────────────────────────
// Welcome banner — modeled on Claude Code's CondensedLogo:
//   left:  small fixed logo block
//   right: name+version, model line, tagline
// We add a single row of "category counts" because OpenProgram users
// want to see "what's loaded right now" without /status. Lists of
// individual items go away — they were the source of the squeezed,
// 30-line welcome the user complained about.
// ──────────────────────────────────────────────────────────────────

const stripAnsi = (s: string): string => s.replace(/\x1b\[[0-9;]*m/g, '');

const visualLength = (s: string): number => stripAnsi(s).length;

const padRight = (s: string, width: number): string => {
  const visible = visualLength(s);
  if (visible >= width) return s;
  return s + ' '.repeat(width - visible);
};

/**
 * Two-line ASCII logo. Sized to align with the four-line text block
 * on the right (logo + blank top/bottom = 4 rows). Tweak only with
 * monospace fonts in mind.
 */
const LOGO_LINES = [
  '   ▗▄▖   ',
  '  ▐▌ ▐▌  ',
  '  ▐▌ ▐▌  ',
  '   ▝▀▘   ',
];

interface WelcomeCounts {
  programs?: number;
  agents?: number;
  sessions?: number;
  tools?: number;
  channels?: number;
}

const collectCounts = (stats: WelcomeStats): WelcomeCounts => {
  const pick = (n?: number, fallback?: number): number | undefined => {
    if (typeof n === 'number') return n;
    if (typeof fallback === 'number') return fallback;
    return undefined;
  };
  return {
    programs: pick(stats.programs_count, stats.top_programs?.length),
    agents: pick(stats.agents_count, stats.top_agents?.length),
    sessions: pick(stats.conversations_count, stats.top_sessions?.length),
    tools: pick(stats.tools_count, stats.top_tools?.length),
    channels: pick(stats.channels_count, stats.top_channels?.length),
  };
};

const formatCountsLine = (c: WelcomeCounts): string => {
  const parts: string[] = [];
  const push = (n: number | undefined, label: string): void => {
    if (typeof n !== 'number') return;
    parts.push(`${BOLD}${FG_ORANGE}${n}${RESET} ${FG_GRAY}${label}${RESET}`);
  };
  push(c.programs, 'programs');
  push(c.agents, 'agents');
  push(c.sessions, 'sessions');
  push(c.tools, 'tools');
  push(c.channels, 'channels');
  return parts.join(`${FG_GRAY} · ${RESET}`);
};

/**
 * Compact welcome banner for the inline REPL. Six lines total: top
 * blank, two logo+name rows, model row, counts row, hint row,
 * bottom blank. Designed to land in scrollback once and stay there
 * — no reflow, no resize sensitivity, no stats list to outgrow the
 * viewport.
 *
 * The function only takes stats (a plain object) and returns an
 * ANSI string. Callers feed it into ``emitToScrollback`` / a plain
 * ``console.log``. Trivial to swap visuals later — none of this is
 * tied to ink components.
 */
export function formatWelcomeText(stats: WelcomeStats): string {
  const agent = stats.agent;
  const counts = collectCounts(stats);

  const right: string[] = [
    `${BOLD}${FG_ORANGE}OpenProgram${RESET}`,
    `${FG_GRAY}${agent?.name ?? '—'} · ${agent?.model ?? '—'}${RESET}`,
    formatCountsLine(counts),
    `${DIM}Type a message and press enter, or type / to browse commands.${RESET}`,
  ];

  const logoWidth = LOGO_LINES[0]?.length ?? 8;
  const out: string[] = [''];
  for (let i = 0; i < LOGO_LINES.length; i++) {
    const left = LOGO_LINES[i] ?? '';
    const text = right[i] ?? '';
    const styledLeft = `${FG_ORANGE}${padRight(left, logoWidth)}${RESET}`;
    out.push(`${styledLeft}  ${text}`);
  }
  out.push('');
  return out.join('\n') + '\n';
}

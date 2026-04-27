import React from 'react';
import { render } from 'ink';
import { REPL } from './screens/REPL.js';
import { BackendClient } from './ws/client.js';
import { ThemeProvider } from './theme/ThemeProvider.js';
import { queryTerminalBg } from './theme/oscQuery.js';
import { setCachedSystemTheme } from './theme/systemTheme.js';

function parseArgs(argv: string[]): { ws: string } {
  let ws = process.env.OPENPROGRAM_WS ?? 'ws://127.0.0.1:8765/ws';
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--ws' && argv[i + 1]) {
      ws = argv[i + 1]!;
      i++;
    }
  }
  return { ws };
}

const { ws } = parseArgs(process.argv.slice(2));
const client = new BackendClient(ws);
client.connect();

// Fire OSC 11 (background-color query) BEFORE Ink renders so we have the
// real terminal bg in hand before stdin gets handed to Ink's input layer.
// Most terminals reply in <50ms; we cap at 200ms and proceed with whatever
// we have. The result lands via setCachedSystemTheme, and ThemeProvider's
// subscriber bumps state so any 'auto' resolution flips to the right
// palette as soon as the answer arrives.
queryTerminalBg(200)
  .then((bg) => { if (bg) setCachedSystemTheme(bg); })
  .catch(() => { /* fall back to COLORFGBG / dark */ });

// Vim / less / htop / tmux startup pattern.
//
// Terminal.app and iTerm2 (with default profile) MERGE the primary-buffer
// scrollback into the altscreen view — so just entering altscreen (\e[?1049h)
// still lets the user mouse-wheel back to whatever was on screen before
// `openprogram` ran. To get the "fresh-canvas" feel users expect from
// vim-style apps, we first wipe the primary buffer:
//   \e[H    cursor home (so \e[3J operates from a known anchor)
//   \e[2J   erase visible viewport
//   \e[3J   erase scrollback (xterm extension; honored by Terminal.app,
//           iTerm2, GNOME Terminal, kitty, Alacritty, Windows Terminal)
// Then we switch to altscreen. On exit we drop back to the (now-empty)
// primary buffer, which leaves the user's shell prompt intact below.
const ENTER_ALT = '\x1b[?1049h';
const EXIT_ALT = '\x1b[?1049l';
const CLEAR_PRIMARY = '\x1b[H\x1b[2J\x1b[3J';
// After \e[?1049h, terminals disagree on the cursor's starting position
// inside altscreen — xterm puts it at (1,1), but Terminal.app preserves
// the pre-switch position. If the shell prompt was at the bottom of the
// terminal, Ink ends up rendering its first frame from that bottom row,
// leaving the top of the screen blank. Force cursor home AFTER entering
// altscreen so Ink writes from row 1 in every emulator. Then clear the
// altscreen view too in case anything (including the OSC 11 reply
// echo on terminals that don't suppress it) printed in the meantime.
process.stdout.write(CLEAR_PRIMARY + ENTER_ALT + '\x1b[2J\x1b[H');

let _altRestored = false;
const restoreScreen = (): void => {
  if (_altRestored) return;
  _altRestored = true;
  try { process.stdout.write(EXIT_ALT); } catch { /* nothing to do on a closed pipe */ }
};
process.on('exit', restoreScreen);
process.on('uncaughtException', (err) => {
  restoreScreen();
  // Re-throw so Node still surfaces the error and exits non-zero.
  throw err;
});

// On resize, repaint the visible viewport. `\e[3J` (clear scrollback) is
// meaningless inside altscreen so we drop it. Ink + Static (keyed on
// resizeNonce in REPL.tsx) re-mounts and re-prints every committed turn
// at the new width.
let _lastCols = process.stdout.columns ?? 0;
let _lastRows = process.stdout.rows ?? 0;
process.stdout.on('resize', () => {
  const cols = process.stdout.columns ?? 0;
  const rows = process.stdout.rows ?? 0;
  if (cols !== _lastCols || rows !== _lastRows) {
    _lastCols = cols;
    _lastRows = rows;
    process.stdout.write('\x1b[2J\x1b[H');
  }
});

process.on('SIGINT', () => process.exit(0));
process.on('SIGTERM', () => process.exit(0));

const { waitUntilExit } = render(
  <ThemeProvider>
    <REPL client={client} />
  </ThemeProvider>,
  { exitOnCtrlC: false },
);

waitUntilExit().then(() => {
  client.close();
  restoreScreen();
  process.exit(0);
});

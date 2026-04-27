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

// We deliberately do NOT enter the alternate screen buffer. altscreen
// gives a clean canvas at startup but loses native scrollback — once
// Ink scrolls past the visible viewport the early turns vanish, and
// the terminal's mouse-wheel scrollback returns the OS shell history
// instead of the chat. Streaming into the primary buffer keeps the
// whole transcript scrollable like a normal terminal app.
//
// On resize, do a full refresh:
//   \e[2J  clear visible viewport
//   \e[3J  clear scrollback buffer (xterm extension; iTerm2 / Terminal /
//          GNOME Terminal / kitty / Windows Terminal honor this)
//   \e[H   cursor home
// Then Ink + Static (which is keyed on resizeNonce in REPL.tsx)
// re-mounts and re-prints every committed turn at the new width. Net
// effect: the user sees a clean reflow at the new size with no fossil
// frames piling up in scrollback.
let _lastCols = process.stdout.columns ?? 0;
let _lastRows = process.stdout.rows ?? 0;
process.stdout.on('resize', () => {
  const cols = process.stdout.columns ?? 0;
  const rows = process.stdout.rows ?? 0;
  if (cols !== _lastCols || rows !== _lastRows) {
    _lastCols = cols;
    _lastRows = rows;
    process.stdout.write('\x1b[2J\x1b[3J\x1b[H');
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
  process.exit(0);
});

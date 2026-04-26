/**
 * Lazy-loaded markdown renderer. The marked + marked-terminal packages
 * are heavy (a few hundred ms of import work because of their internal
 * regex compilation and language tables) — and totally cold at startup.
 * Defer the import until the first assistant reply actually needs
 * formatting, so `openprogram` boots into the input box faster.
 */

type MarkedFn = (text: string) => string;
let _renderer: MarkedFn | null = null;

const buildRenderer = (): MarkedFn => {
  // require() rather than import() because esbuild bundles both into
  // the same chunk anyway, and require is synchronous (the first call
  // pays the loading cost on demand instead of awaiting). createRequire
  // is set up by our esbuild banner.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { marked } = require('marked');
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { markedTerminal } = require('marked-terminal');
  marked.use(markedTerminal());
  return (text: string) => {
    try {
      const out = marked.parse(text) as string;
      return out.replace(/\n+$/, '');
    } catch {
      return text;
    }
  };
};

/**
 * Convert a markdown string into ANSI text for terminal display.
 *
 * The first call lazily loads marked + marked-terminal; subsequent calls
 * reuse the cached renderer. Falls back to the raw input on any parse
 * error so a bad fence can't swallow the assistant's reply.
 */
export const renderMarkdown = (text: string): string => {
  if (!_renderer) _renderer = buildRenderer();
  return _renderer(text);
};

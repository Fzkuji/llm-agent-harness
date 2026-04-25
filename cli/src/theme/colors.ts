/**
 * Semantic theme tokens used across the Ink TUI.
 *
 * Palette: warm orange-red. Swap the values here to reskin without
 * touching component code.
 */
export const colors = {
  // Common roles --------------------------------------------------------
  primary: '#ff7a45',     // warm orange — used for accents, prompt arrow, headings
  secondary: '#888888',
  success: '#7ad17a',      // muted green for assistant glyph
  warning: '#ffb86c',      // soft amber for spinners, working tag
  error: '#e25c4d',        // brick red
  muted: '#9c9c9c',
  accent: '#d76b3a',
  text: '#f0f0f0',
  border: '#5a5a5a',

  // Chat-turn roles -----------------------------------------------------
  user: {
    /** Hex used as the user-message block background. Subtle warm tint. */
    bg: '#3a2118',
    fg: '#f5e8da',
    glyph: '#ff7a45',
  },
  assistant: {
    bg: undefined as string | undefined,
    fg: '#f0f0f0',
    glyph: '#7ad17a',
  },
  system: {
    bg: undefined as string | undefined,
    fg: '#9c9c9c',
    glyph: '#9c9c9c',
  },

  // Tool-call rendering -------------------------------------------------
  tool: {
    running: '#ffb86c',
    done: '#9c9c9c',
    error: '#e25c4d',
  },
} as const;

export type ColorTheme = typeof colors;

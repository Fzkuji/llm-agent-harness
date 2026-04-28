/**
 * <Shell> — root component for OpenProgram TUI screens.
 *
 * Wraps AlternateScreen and applies the global flex root so children
 * can use ``flexGrow`` to fill available height. Provides the
 * outermost <Box> that everything else lives inside, plus the
 * standard ``height={rows}`` so child <ScrollView> components have a
 * concrete height to grow into (without it, ScrollBox falls back to
 * children's intrinsic height and overflow:scroll never kicks in).
 *
 * Use it like this:
 *
 *     <Shell>
 *       <ScrollView>
 *         {messages.map(m => <MessageRow ...>)}
 *       </ScrollView>
 *       <PromptInput />
 *       <BottomBar />
 *     </Shell>
 *
 * The Shell takes care of:
 *   - entering AlternateScreen (so output doesn't pollute scrollback)
 *   - sizing root to terminal rows×cols (so flex math works)
 *   - reactive resize via useTerminalSize (drives everything in tree)
 *   - mouse tracking opt-in (off by default — old terminals trip on it)
 *
 * The Shell DOES NOT provide modal/toast contexts yet; phase 2 adds
 * <UIProviders> which wraps Shell with those.
 */
import React, { type ReactNode } from 'react';
import { AlternateScreen, Box, useTerminalSize } from '@openprogram/ink';

export interface ShellProps {
  children: ReactNode;
  /** Enable SGR mouse tracking (wheel + click). Default off. Some
   * older terminals (Apple Terminal) and SSH-via-tmux setups don't
   * play nicely. Off keeps the keyboard-only path bulletproof. */
  mouseTracking?: boolean;
}

const ShellInner: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { columns, rows } = useTerminalSize();
  return (
    <Box
      flexDirection="column"
      width={columns}
      height={rows}
    >
      {children}
    </Box>
  );
};

export const Shell: React.FC<ShellProps> = ({ children, mouseTracking = false }) => (
  <AlternateScreen mouseTracking={mouseTracking}>
    <ShellInner>{children}</ShellInner>
  </AlternateScreen>
);

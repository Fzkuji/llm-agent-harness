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
import { AlternateScreen, Box, useInput, useTerminalSize } from '@openprogram/ink';
import { ModalProvider, useModal } from './ModalProvider.js';

export interface ShellProps {
  children: ReactNode;
  /** Enable SGR mouse tracking (wheel + click). Default off. Some
   * older terminals (Apple Terminal) and SSH-via-tmux setups don't
   * play nicely. Off keeps the keyboard-only path bulletproof. */
  mouseTracking?: boolean;
}

/**
 * Listens for esc and pops the top-of-stack modal. Lives inside the
 * ModalProvider so a fresh handler runs whenever the stack changes
 * (no stale closures over an empty stack).
 *
 * We deliberately do NOT swallow esc when the stack is empty — the
 * legacy PromptInput / pickers still consume their own esc for
 * inline cancel actions.
 */
const ModalEscHandler: React.FC = () => {
  const modal = useModal();
  useInput((_input, key) => {
    if (key.escape && modal.stack.length > 0) {
      modal.pop();
    }
  });
  return null;
};

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
    <ModalProvider>
      <ModalEscHandler />
      <ShellInner>{children}</ShellInner>
    </ModalProvider>
  </AlternateScreen>
);

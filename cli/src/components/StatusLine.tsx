import React from 'react';
import { Box, Text } from 'ink';
import { colors } from '../theme/colors.js';

export interface StatusLineProps {
  agent?: string;
  model?: string;
  conversationId: string;
  busy?: boolean;
}

export const StatusLine: React.FC<StatusLineProps> = ({ agent, model, conversationId, busy }) => {
  return (
    <Box paddingX={1}>
      <Text color={colors.muted}>
        {agent ?? '—'} <Text color={colors.border}>·</Text> {model ?? '—'}{' '}
        <Text color={colors.border}>·</Text> {conversationId.slice(0, 12)}
        {busy ? (
          <>
            {' '}
            <Text color={colors.warning}>● working</Text>
          </>
        ) : null}
      </Text>
    </Box>
  );
};

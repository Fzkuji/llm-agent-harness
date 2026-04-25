import React from 'react';
import { Box, Text } from 'ink';
import type { UIMessage } from '../screens/REPL.js';
import { colors } from '../theme/colors.js';

export interface MessagesProps {
  items: UIMessage[];
}

const roleLabel = (role: UIMessage['role'], tag?: string): { label: string; color: string } => {
  if (role === 'user') return { label: tag ? `User (${tag})` : 'User', color: colors.primary };
  if (role === 'assistant') return { label: 'Assistant', color: colors.success };
  return { label: 'System', color: colors.muted };
};

export const Messages: React.FC<MessagesProps> = ({ items }) => {
  return (
    <Box flexDirection="column" paddingX={1}>
      {items.map((m) => {
        const { label, color } = roleLabel(m.role, m.tag);
        return (
          <Box key={m.id} flexDirection="column" marginBottom={1}>
            <Text bold color={color}>
              {label}
            </Text>
            <Text>{m.text}</Text>
          </Box>
        );
      })}
    </Box>
  );
};

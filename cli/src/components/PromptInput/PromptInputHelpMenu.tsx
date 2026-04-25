import React from 'react';
import { Box, Text } from 'ink';
import { colors } from '../../theme/colors.js';
import { SLASH_COMMANDS } from '../../commands/registry.js';

export interface PromptInputHelpMenuProps {
  filter: string;
}

export const PromptInputHelpMenu: React.FC<PromptInputHelpMenuProps> = ({ filter }) => {
  const needle = filter.replace(/^\//, '').toLowerCase();
  const items = SLASH_COMMANDS.filter((c) => !needle || c.name.toLowerCase().includes(needle));
  if (items.length === 0) {
    return (
      <Box paddingX={1}>
        <Text color={colors.muted}>(no matching commands)</Text>
      </Box>
    );
  }
  return (
    <Box flexDirection="column" paddingX={1}>
      {items.slice(0, 12).map((c) => (
        <Box key={c.name}>
          <Box width={18}>
            <Text color={colors.primary}>/{c.name}</Text>
          </Box>
          <Text color={colors.muted}>{c.description}</Text>
        </Box>
      ))}
    </Box>
  );
};

import React from 'react';
import { Box, Text } from 'ink';
import { colors } from '../theme/colors.js';

export interface WelcomeStats {
  agent?: { id?: string; name?: string; model?: string } | null;
  agents_count?: number;
  programs_count?: number;
  skills_count?: number;
  conversations_count?: number;
}

export interface WelcomeProps {
  stats?: WelcomeStats;
}

const dim = (n?: number) => (typeof n === 'number' ? String(n) : '—');

export const Welcome: React.FC<WelcomeProps> = ({ stats }) => {
  const agentName = stats?.agent?.name ?? stats?.agent?.id ?? '—';
  const model = stats?.agent?.model ?? '—';

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={colors.primary}
      paddingX={2}
      paddingY={0}
      marginBottom={1}
    >
      <Text bold color={colors.primary}>
        OpenProgram
      </Text>
      <Box marginTop={0}>
        <Text color={colors.muted}>
          agent <Text color={colors.text}>{agentName}</Text>
          <Text color={colors.border}> · </Text>
          model <Text color={colors.text}>{model}</Text>
        </Text>
      </Box>
      <Box>
        <Text color={colors.muted}>
          <Text color={colors.text}>{dim(stats?.programs_count)}</Text> programs
          <Text color={colors.border}> · </Text>
          <Text color={colors.text}>{dim(stats?.skills_count)}</Text> skills
          <Text color={colors.border}> · </Text>
          <Text color={colors.text}>{dim(stats?.agents_count)}</Text> agents
          <Text color={colors.border}> · </Text>
          <Text color={colors.text}>{dim(stats?.conversations_count)}</Text> sessions
        </Text>
      </Box>
      <Box marginTop={1}>
        <Text color={colors.muted}>
          Type a message and press <Text color={colors.primary}>enter</Text>, or{' '}
          <Text color={colors.primary}>/</Text> to browse commands.
        </Text>
      </Box>
    </Box>
  );
};

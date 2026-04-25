import React from 'react';
import { Box, Text } from 'ink';
import { colors } from '../theme/colors.js';

export type Role = 'user' | 'assistant' | 'system';

export interface ToolCall {
  id: string;
  tool: string;
  input?: string;
  result?: string;
  status: 'running' | 'done' | 'error';
}

export interface Turn {
  id: string;
  role: Role;
  text: string;
  /** Inline tool calls between text segments. Order is preserved by .order. */
  tools?: ToolCall[];
  tag?: string;
}

const barColor = (role: Role): string => {
  if (role === 'user') return colors.primary;
  if (role === 'assistant') return colors.success;
  return colors.muted;
};

const Bar: React.FC<{ role: Role }> = ({ role }) => (
  <Box flexDirection="column" marginRight={1}>
    <Text color={barColor(role)}>▎</Text>
  </Box>
);

const ToolRow: React.FC<{ call: ToolCall }> = ({ call }) => {
  const arrow =
    call.status === 'running' ? '◌' : call.status === 'error' ? '✗' : '●';
  const color =
    call.status === 'running'
      ? colors.warning
      : call.status === 'error'
      ? colors.error
      : colors.muted;
  const inputPreview = call.input ? ` ${call.input.slice(0, 80)}` : '';
  return (
    <Box paddingLeft={2}>
      <Text color={color}>{arrow} </Text>
      <Text color={colors.text} bold>
        {call.tool}
      </Text>
      <Text color={colors.muted}>{inputPreview}</Text>
    </Box>
  );
};

export const TurnRow: React.FC<{ turn: Turn }> = ({ turn }) => {
  const lines = turn.text.split('\n');
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box>
        <Bar role={turn.role} />
        <Box flexDirection="column" flexGrow={1}>
          {turn.tag ? (
            <Text color={colors.muted}>
              <Text color={barColor(turn.role)}>{turn.role}</Text>
              <Text color={colors.border}> · </Text>
              {turn.tag}
            </Text>
          ) : null}
          {lines.map((l, i) => (
            <Text key={i}>{l || ' '}</Text>
          ))}
        </Box>
      </Box>
      {turn.tools && turn.tools.length > 0 ? (
        <Box flexDirection="column" marginTop={0}>
          {turn.tools.map((t) => (
            <ToolRow key={t.id} call={t} />
          ))}
        </Box>
      ) : null}
    </Box>
  );
};

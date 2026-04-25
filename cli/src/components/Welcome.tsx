import React from 'react';
import { Box, Text } from 'ink';
import { colors } from '../theme/colors.js';
import { useTerminalWidth, usePanelWidth, useTerminalHeight } from '../utils/useTerminalWidth.js';

export interface WelcomeStats {
  agent?: { id?: string; name?: string; model?: string } | null;
  agents_count?: number;
  programs_count?: number;
  skills_count?: number;
  conversations_count?: number;
  top_programs?: Array<{ name?: string; category?: string }>;
  top_skills?: Array<{ name?: string; slug?: string }>;
  top_agents?: Array<{ name?: string; id?: string }>;
  top_sessions?: Array<{ id?: string; title?: string }>;
  top_tools?: string[];
  top_providers?: string[];
  top_channels?: Array<{ channel?: string; id?: string }>;
}

export interface WelcomeProps {
  stats?: WelcomeStats;
}

const fmt = (n?: number): string => (typeof n === 'number' ? String(n) : '—');

interface ColumnSpec {
  count: string;
  label: string;
  items: string[];
}

const Column: React.FC<{
  spec: ColumnSpec;
  width: number;
  /** When true, items wrap into 2 sub-columns inside the column. */
  twoCols: boolean;
  /** Cap on number of item rows shown (truncates with "+N more"). */
  maxRows: number;
}> = ({ spec, width, twoCols, maxRows }) => {
  const innerWidth = Math.max(8, width - 2);
  const subWidth = twoCols ? Math.floor(innerWidth / 2) : innerWidth;
  const limitedItems = spec.items.slice(0, twoCols ? maxRows * 2 : maxRows);
  const overflow = spec.items.length - limitedItems.length;
  const rows: Array<[string, string | undefined]> = [];
  if (twoCols) {
    const half = Math.ceil(limitedItems.length / 2);
    for (let i = 0; i < half; i++) {
      rows.push([limitedItems[i] ?? '', limitedItems[i + half]]);
    }
  } else {
    for (const it of limitedItems) rows.push([it, undefined]);
  }
  return (
    <Box flexDirection="column" width={width} paddingX={1}>
      <Box justifyContent="center">
        <Text bold color={colors.primary}>
          {spec.count}
        </Text>
      </Box>
      <Box justifyContent="center">
        <Text color={colors.muted}>{spec.label}</Text>
      </Box>
      {rows.map(([a, b], i) => (
        <Box key={i}>
          <Box width={subWidth}>
            <Text color={colors.muted} wrap="truncate-end">
              {a}
            </Text>
          </Box>
          {twoCols && b ? (
            <Box width={subWidth}>
              <Text color={colors.muted} wrap="truncate-end">
                {b}
              </Text>
            </Box>
          ) : null}
        </Box>
      ))}
      {overflow > 0 ? (
        <Text color={colors.border}>  +{overflow}</Text>
      ) : null}
    </Box>
  );
};

export const Welcome: React.FC<WelcomeProps> = ({ stats }) => {
  const cols = useTerminalWidth();
  const rows = useTerminalHeight();
  const width = usePanelWidth();
  const agentName = stats?.agent?.name ?? stats?.agent?.id ?? '—';
  const model = stats?.agent?.model ?? '—';

  const programs: ColumnSpec = {
    count: fmt(stats?.programs_count),
    label: 'programs',
    items: (stats?.top_programs ?? [])
      .map((p) => p.name)
      .filter((s): s is string => !!s),
  };
  const skills: ColumnSpec = {
    count: fmt(stats?.skills_count),
    label: 'skills',
    items: (stats?.top_skills ?? [])
      .map((s) => s.name)
      .filter((s): s is string => !!s),
  };
  const agentsCol: ColumnSpec = {
    count: fmt(stats?.agents_count),
    label: 'agents',
    items: (stats?.top_agents ?? [])
      .map((a) => a.name ?? a.id)
      .filter((s): s is string => !!s),
  };
  const sessionsCol: ColumnSpec = {
    count: fmt(stats?.conversations_count),
    label: 'sessions',
    items: (stats?.top_sessions ?? [])
      .map((s) => s.title ?? s.id)
      .filter((s): s is string => !!s),
  };
  const tools: ColumnSpec = {
    count: fmt(stats?.top_tools?.length),
    label: 'tools',
    items: stats?.top_tools ?? [],
  };
  const providers: ColumnSpec = {
    count: fmt(stats?.top_providers?.length),
    label: 'providers',
    items: stats?.top_providers ?? [],
  };
  const channels: ColumnSpec = {
    count: fmt(stats?.top_channels?.length),
    label: 'channels',
    items: (stats?.top_channels ?? []).map((c) =>
      c.channel && c.id ? `${c.channel}:${c.id}` : c.channel ?? c.id ?? '',
    ),
  };

  // Layout decisions based on terminal width.
  // - cols < 50 : 2 cols × 2 rows of headline tiles, no extras row
  // - cols 50-100: single-row 4 tiles + extras row (3 tiles)
  // - cols >= 100: same, items get a 2-sub-column layout per tile
  const compact = cols < 50;
  const twoSubCols = cols >= 110;

  // Vertical budget. Other UI elements consume ~6-8 rows (input box +
  // bottom bar + spinner + safety margin). Whatever remains we spend on
  // welcome content: title, gaps, two header rows (count + label), N item
  // rows per tile, optional extras row, tip, padding+border.
  const reservedRows = 8;
  const available = Math.max(8, rows - reservedRows);
  // Per-tile fixed cost = count + label + (extras gap) ≈ 3.
  // With one row of headline tiles + tip line ≈ 6 fixed rows.
  // Items budget = available - 6 (single row) or - 9 (two rows).
  const headlineFixed = 5; // title row + count + label + tip + gap
  const extrasFixed = 4; // count + label + gap + (margin row)
  const showExtras = available >= headlineFixed + extrasFixed + 4;
  const itemsRowsForHeadline = Math.max(
    1,
    Math.min(8, available - headlineFixed - (showExtras ? extrasFixed : 0)),
  );
  const itemsRowsForExtras = showExtras
    ? Math.max(1, Math.min(4, available - headlineFixed - extrasFixed - itemsRowsForHeadline + 2))
    : 0;

  const headlineCols: ColumnSpec[] = compact
    ? []
    : [programs, skills, agentsCol, sessionsCol];
  const headlineColWidth = compact
    ? Math.floor((width - 4) / 2)
    : Math.floor((width - 4) / 4);

  const extrasCols: ColumnSpec[] = compact
    ? [programs, skills, agentsCol, sessionsCol, tools, providers, channels]
    : [tools, providers, channels];
  const extrasColWidth = compact
    ? Math.floor((width - 4) / 2)
    : Math.floor((width - 4) / 3);

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={colors.primary}
      paddingX={2}
      paddingY={0}
      marginBottom={1}
      width={width}
    >
      {/* Title row */}
      <Box justifyContent="space-between">
        <Text bold color={colors.primary}>
          OpenProgram
        </Text>
        <Text color={colors.muted}>
          {agentName} <Text color={colors.border}>·</Text> {model}
        </Text>
      </Box>

      {/* Headline row — 4 main tiles with vertical item lists */}
      {headlineCols.length > 0 ? (
        <Box marginTop={1}>
          {headlineCols.map((c) => (
            <Column
              key={c.label}
              spec={c}
              width={headlineColWidth}
              twoCols={twoSubCols}
              maxRows={itemsRowsForHeadline}
            />
          ))}
        </Box>
      ) : null}

      {/* Compact: pack everything into 2-col grid; otherwise extras row */}
      {compact ? (
        <Box flexDirection="column" marginTop={1}>
          {Array.from({ length: Math.ceil(extrasCols.length / 2) }).map((_, row) => (
            <Box key={row}>
              {extrasCols.slice(row * 2, row * 2 + 2).map((c) => (
                <Column
                  key={c.label}
                  spec={c}
                  width={extrasColWidth}
                  twoCols={false}
                  maxRows={Math.max(1, itemsRowsForHeadline - 1)}
                />
              ))}
            </Box>
          ))}
        </Box>
      ) : showExtras ? (
        <Box marginTop={1}>
          {extrasCols.map((c) => (
            <Column
              key={c.label}
              spec={c}
              width={extrasColWidth}
              twoCols={twoSubCols}
              maxRows={itemsRowsForExtras}
            />
          ))}
        </Box>
      ) : null}

      <Box marginTop={1}>
        <Text color={colors.muted}>
          Type a message and press <Text color={colors.primary}>enter</Text>, or type{' '}
          <Text color={colors.primary}>/</Text> to browse commands.
        </Text>
      </Box>
    </Box>
  );
};

import React, { useState, useEffect } from 'react';
import { Box, Text, useInput } from 'ink';
import { colors } from '../theme/colors.js';
import { usePanelWidth } from '../utils/useTerminalWidth.js';

export interface PickerItem<V> {
  /** Display name in the list. */
  label: string;
  /** Optional secondary line shown next to label, dim. */
  description?: string;
  /** Value handed to onSelect. */
  value: V;
}

export interface PickerProps<V> {
  title: string;
  items: PickerItem<V>[];
  onSelect: (item: PickerItem<V>) => void;
  onCancel: () => void;
  /** Optional max number of rows shown at once before windowing. */
  maxVisible?: number;
}

export function Picker<V>({ title, items, onSelect, onCancel, maxVisible = 10 }: PickerProps<V>): React.ReactElement {
  const [index, setIndex] = useState(0);
  const [filter, setFilter] = useState('');

  // Filter items by typed text. Match against label + description.
  const needle = filter.toLowerCase();
  const filtered = needle
    ? items.filter(
        (it) =>
          it.label.toLowerCase().includes(needle) ||
          (it.description?.toLowerCase().includes(needle) ?? false),
      )
    : items;

  useEffect(() => {
    if (index >= filtered.length) setIndex(0);
  }, [filtered.length, index]);

  useInput((input, key) => {
    if (key.escape) {
      onCancel();
      return;
    }
    if (key.return) {
      const it = filtered[index];
      if (it) onSelect(it);
      return;
    }
    if (key.upArrow) {
      setIndex((i) => (i - 1 + filtered.length) % Math.max(1, filtered.length));
      return;
    }
    if (key.downArrow) {
      setIndex((i) => (i + 1) % Math.max(1, filtered.length));
      return;
    }
    if (key.backspace || key.delete) {
      setFilter((f) => f.slice(0, -1));
      return;
    }
    if (input && !key.ctrl && !key.meta) {
      setFilter((f) => f + input);
    }
  });

  // Window the visible slice around the cursor.
  const half = Math.floor(maxVisible / 2);
  let start = Math.max(0, index - half);
  const end = Math.min(filtered.length, start + maxVisible);
  if (end - start < maxVisible) start = Math.max(0, end - maxVisible);
  const visible = filtered.slice(start, end);

  // Width: track the panel cap so Picker doesn't burst on wide
  // terminals or break on narrow ones.
  const panelWidth = usePanelWidth();
  const labelWidth = Math.max(8, Math.min(28, Math.floor(panelWidth / 3)));

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={colors.primary}
      paddingX={1}
      marginBottom={1}
      width={panelWidth}
    >
      <Box justifyContent="space-between">
        <Text bold color={colors.primary}>
          {title}
        </Text>
        <Text color={colors.muted}>
          {filter ? <Text>filter: {filter}</Text> : null}
          {filter ? <Text color={colors.border}> · </Text> : null}
          {filtered.length === 0 ? '(no matches)' : `${index + 1}/${filtered.length}`}
        </Text>
      </Box>
      {visible.map((it, i) => {
        const idx = start + i;
        const selected = idx === index;
        return (
          <Box key={`${idx}-${it.label}`}>
            <Text color={selected ? colors.primary : colors.border}>
              {selected ? '▌ ' : '  '}
            </Text>
            <Box width={labelWidth}>
              <Text color={selected ? colors.primary : colors.text} bold={selected}>
                {it.label}
              </Text>
            </Box>
            {it.description ? (
              <Text color={selected ? colors.text : colors.muted} wrap="truncate-end">
                {it.description}
              </Text>
            ) : null}
          </Box>
        );
      })}
      <Text color={colors.muted}>type to filter · ↑↓ choose · enter pick · esc cancel</Text>
    </Box>
  );
}

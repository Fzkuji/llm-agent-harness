import React, { useState } from 'react';
import { Box, Text } from 'ink';
import TextInput from 'ink-text-input';
import { PromptInputHelpMenu } from './PromptInputHelpMenu.js';
import { PromptInputFooter } from './PromptInputFooter.js';
import { colors } from '../../theme/colors.js';

export interface PromptInputProps {
  onSubmit: (text: string) => void;
  busy?: boolean;
}

export const PromptInput: React.FC<PromptInputProps> = ({ onSubmit, busy }) => {
  const [value, setValue] = useState('');

  const showHelp = value.startsWith('/');

  const handleSubmit = (text: string) => {
    if (busy) return;
    setValue('');
    onSubmit(text);
  };

  return (
    <Box flexDirection="column">
      {showHelp ? <PromptInputHelpMenu filter={value} /> : null}
      <Box
        borderStyle="round"
        borderColor={busy ? colors.warning : colors.primary}
        paddingX={1}
      >
        <Text color={colors.primary}>{'> '}</Text>
        <TextInput value={value} onChange={setValue} onSubmit={handleSubmit} />
      </Box>
      <PromptInputFooter />
    </Box>
  );
};

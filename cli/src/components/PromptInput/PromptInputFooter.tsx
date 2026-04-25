import React from 'react';
import { Box, Text } from 'ink';
import { colors } from '../../theme/colors.js';

export const PromptInputFooter: React.FC = () => {
  return (
    <Box paddingX={1}>
      <Text color={colors.muted}>
        / commands · enter send · ctrl+c quit
      </Text>
    </Box>
  );
};

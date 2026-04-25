import React from 'react';
import { Static } from 'ink';
import { TurnRow, Turn } from './Turn.js';

export interface MessagesProps {
  /** Frozen committed turns — Ink prints them once and never re-renders. */
  committed: Turn[];
  /** Currently-streaming assistant turn, if any. Re-renders every delta. */
  streaming?: Turn | null;
}

export const Messages: React.FC<MessagesProps> = ({ committed, streaming }) => {
  return (
    <>
      <Static items={committed}>{(t) => <TurnRow key={t.id} turn={t} />}</Static>
      {streaming ? <TurnRow turn={streaming} /> : null}
    </>
  );
};

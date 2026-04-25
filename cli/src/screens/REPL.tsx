import React, { useEffect, useState } from 'react';
import { Box, useApp, useInput } from 'ink';
import { BackendClient, WsEnvelope } from '../ws/client.js';
import { StatusLine } from '../components/StatusLine.js';
import { Messages } from '../components/Messages.js';
import { PromptInput } from '../components/PromptInput/PromptInput.js';

export interface REPLProps {
  client: BackendClient;
  initialAgent?: string;
  initialConversation?: string;
}

export interface UIMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  text: string;
  tag?: string;
}

interface AgentInfo {
  id: string;
  name: string;
  model?: string | { provider?: string; id?: string };
  default?: boolean;
}

const renderModel = (m: AgentInfo['model']): string | undefined => {
  if (!m) return undefined;
  if (typeof m === 'string') return m;
  return m.id ?? m.provider;
};

export const REPL: React.FC<REPLProps> = ({ client, initialAgent, initialConversation }) => {
  const app = useApp();
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [agent, setAgent] = useState<string | undefined>(initialAgent);
  const [model, setModel] = useState<string | undefined>(undefined);
  const [conversationId, setConversationId] = useState<string | undefined>(initialConversation);
  const [busy, setBusy] = useState(false);
  const [pendingMsgId, setPendingMsgId] = useState<string | null>(null);

  useEffect(() => {
    const off = client.on((ev: WsEnvelope) => {
      if (ev.type === 'chat_ack') {
        setConversationId(ev.data.conv_id);
        setPendingMsgId(ev.data.msg_id);
      } else if (ev.type === 'chat_response') {
        const d = ev.data;
        if (d.type === 'stream_event' && typeof d.content === 'string') {
          appendStream(d.content);
        } else if (d.type === 'result' && typeof d.content === 'string') {
          replaceOrAppendAssistant(d.content);
          setBusy(false);
          setPendingMsgId(null);
        } else if (d.type === 'error' && typeof d.content === 'string') {
          setMessages((m) => [...m, { id: `e-${Date.now()}`, role: 'system', text: `error: ${d.content}` }]);
          setBusy(false);
          setPendingMsgId(null);
        } else if (d.type === 'status' && typeof d.content === 'string') {
          setMessages((m) => [...m, { id: `s-${Date.now()}`, role: 'system', text: d.content as string }]);
        }
      } else if (ev.type === 'agents_list') {
        const list = ev.data as AgentInfo[];
        setAgents(list);
        const def = list.find((a) => a.default) ?? list[0];
        if (def && !agent) {
          setAgent(def.id);
          const m = renderModel(def.model);
          if (m) setModel(m);
        }
      } else if (ev.type === 'event') {
        const e = ev as { type: 'event'; event: string; data: Record<string, unknown> };
        if (e.event === 'agents') {
          client.send({ action: 'list_agents' });
        }
      } else if (ev.type === 'error') {
        const data = (ev as { data?: { message?: string } }).data;
        const msg = data?.message ?? 'unknown error';
        setMessages((m) => [...m, { id: `e-${Date.now()}`, role: 'system', text: `error: ${msg}` }]);
      }
    });
    client.send({ action: 'sync' });
    client.send({ action: 'list_agents' });
    return () => {
      off();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client]);

  const appendStream = (delta: string) => {
    setMessages((m) => {
      const last = m[m.length - 1];
      if (last && last.role === 'assistant' && last.id.startsWith('a-stream')) {
        return [...m.slice(0, -1), { ...last, text: last.text + delta }];
      }
      return [...m, { id: `a-stream-${Date.now()}`, role: 'assistant', text: delta }];
    });
  };

  const replaceOrAppendAssistant = (text: string) => {
    setMessages((m) => {
      const last = m[m.length - 1];
      if (last && last.role === 'assistant' && last.id.startsWith('a-stream')) {
        return [...m.slice(0, -1), { ...last, id: `a-${Date.now()}`, text }];
      }
      return [...m, { id: `a-${Date.now()}`, role: 'assistant', text }];
    });
  };

  useInput((input, key) => {
    if (key.ctrl && input === 'c') {
      app.exit();
    }
  });

  const onSubmit = (text: string) => {
    if (!text.trim()) return;
    setMessages((m) => [...m, { id: `u-${Date.now()}`, role: 'user', text }]);
    setBusy(true);
    client.send({
      action: 'chat',
      conv_id: conversationId,
      agent_id: agent,
      text,
    });
  };

  return (
    <Box flexDirection="column">
      <Messages items={messages} />
      <PromptInput onSubmit={onSubmit} busy={busy} />
      <StatusLine agent={agent} model={model} conversationId={conversationId ?? '(new)'} busy={busy} />
    </Box>
  );
};

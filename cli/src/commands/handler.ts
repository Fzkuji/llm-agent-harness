import { BackendClient } from '../ws/client.js';
import { SLASH_COMMANDS } from './registry.js';

export interface SlashContext {
  client: BackendClient;
  pushUser: () => void;
  pushSystem: (text: string) => void;
  clearCommitted: () => void;
  newSession: () => void;
  exit: () => void;
  currentAgent?: string;
  currentModel?: string;
  currentConversation?: string;
}

const helpText = (): string => {
  const lines = ['Available commands:'];
  for (const c of SLASH_COMMANDS) {
    lines.push(`  /${c.name.padEnd(14)} ${c.description}`);
  }
  return lines.join('\n');
};

const attachUsage = (
  'Usage: /attach <channel> <account> <peer>\n' +
  '  channel : wechat | telegram | discord | slack\n' +
  '  account : the account_id you registered (e.g. "default", "work")\n' +
  '  peer    : the channel-side user/chat id (wxid_xxx, chat_id, …)\n' +
  '\n' +
  'After attach, that peer\'s inbound messages route into the current\n' +
  'session instead of the agent.session_scope default.'
);

const detachUsage = (
  'Usage: /detach <channel> <account> <peer>'
);

const tokenize = (s: string): string[] =>
  s.trim().split(/\s+/).filter((x) => x.length > 0);

/**
 * Try to handle a slash line in-process. Returns true when the command was
 * recognized (caller should NOT forward it to the LLM); false to forward as
 * a plain chat message.
 */
export function handleSlash(line: string, ctx: SlashContext): boolean {
  const tokens = tokenize(line);
  if (tokens.length === 0 || !tokens[0]?.startsWith('/')) return false;
  const cmd = tokens[0]!.slice(1).toLowerCase();
  const args = tokens.slice(1);

  switch (cmd) {
    case 'help':
      ctx.pushUser();
      ctx.pushSystem(helpText());
      return true;

    case 'clear':
      ctx.clearCommitted();
      return true;

    case 'quit':
    case 'exit':
      ctx.exit();
      return true;

    case 'new': {
      ctx.newSession();
      ctx.pushSystem('Started a new session.');
      return true;
    }

    case 'session': {
      const lines = [
        `agent          : ${ctx.currentAgent ?? '—'}`,
        `model          : ${ctx.currentModel ?? '—'}`,
        `conversation   : ${ctx.currentConversation ?? '(new)'}`,
      ];
      ctx.pushUser();
      ctx.pushSystem(lines.join('\n'));
      return true;
    }

    case 'agents': {
      ctx.pushUser();
      ctx.client.send({ action: 'list_agents' });
      ctx.pushSystem('Listing agents… (see sidebar update once received)');
      return true;
    }

    case 'connections': {
      ctx.pushUser();
      ctx.client.send({ action: 'list_channel_bindings' });
      ctx.pushSystem('Listing channel bindings…');
      return true;
    }

    case 'aliases':
    case 'sessions': {
      ctx.pushUser();
      ctx.client.send({
        action: cmd === 'aliases' ? 'list_session_aliases' : 'list_conversations',
      });
      ctx.pushSystem(`Requested ${cmd}.`);
      return true;
    }

    case 'attach': {
      ctx.pushUser();
      if (args.length < 3) {
        ctx.pushSystem(attachUsage);
        return true;
      }
      const [channel, account_id, peer] = args as [string, string, string];
      if (!ctx.currentConversation) {
        ctx.pushSystem('No current conversation. Send a message first to create one.');
        return true;
      }
      ctx.client.send({
        action: 'attach_session',
        channel,
        account_id,
        peer,
        conversation_id: ctx.currentConversation,
      });
      ctx.pushSystem(
        `Attached ${channel}:${account_id}:${peer} → ${ctx.currentConversation}`,
      );
      return true;
    }

    case 'detach': {
      ctx.pushUser();
      if (args.length < 3) {
        ctx.pushSystem(detachUsage);
        return true;
      }
      const [channel, account_id, peer] = args as [string, string, string];
      ctx.client.send({ action: 'detach_session', channel, account_id, peer });
      ctx.pushSystem(`Detached ${channel}:${account_id}:${peer}`);
      return true;
    }

    case 'agent': {
      ctx.pushUser();
      if (args.length < 1) {
        ctx.pushSystem('Usage: /agent <agent_id>');
        return true;
      }
      const id = args[0]!;
      ctx.client.send({ action: 'set_default_agent', id });
      ctx.pushSystem(`Set default agent → ${id}`);
      return true;
    }

    default:
      // Unknown slash command: treat as chat. Server may reject or the LLM
      // may handle it. We still forward so the user can see what happened.
      return false;
  }
}

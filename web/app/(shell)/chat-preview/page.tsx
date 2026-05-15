"use client";

/**
 * Component preview harness for the message-stream port (phase 2).
 *
 * Seeds the session store with fixture messages covering every bubble
 * state, then renders the real `<MessageList />` against them. Lets
 * each component be eyeballed in isolation before the phase-3 cutover
 * touches the live chat. Throwaway route — deleted once phase 3 lands.
 */
import { useEffect, useState } from "react";

import { MessageList } from "@/components/chat/messages/message-list";
import { useSessionStore, type ChatMsg } from "@/lib/session-store";

const PREVIEW_SID = "__preview__";

const FIXTURES: ChatMsg[] = [
  {
    id: "u1",
    role: "user",
    content: "Summarise what changed in the auth module this week.",
    status: "done",
  },
  {
    id: "a1",
    role: "assistant",
    content:
      "Here's a quick rundown:\n\n- **Token rotation** is now automatic\n- The `login()` path validates `aud` claims\n- Added `requireRole()` middleware\n\n```ts\nrequireRole('admin')\n```",
    status: "done",
  },
  {
    id: "a2",
    role: "assistant",
    content: "Done — I checked the three files and they all line up.",
    thinking:
      "Let me trace the call path. login() → verifyToken() → decodeClaims().\nThe aud check was added in verifyToken, line 41. Looks consistent.",
    status: "done",
  },
  {
    id: "a3",
    role: "assistant",
    content: "I ran the tools and here is the result.",
    tools: [
      {
        id: "t1",
        tool: "read_file",
        input: '{"path": "src/auth/login.ts"}',
        result: "export function login() { /* ... 80 lines ... */ }",
        status: "done",
      },
      {
        id: "t2",
        tool: "grep",
        input: '{"pattern": "requireRole", "path": "src"}',
        result: "src/auth/mw.ts:12: export function requireRole(role) {",
        status: "done",
      },
      {
        id: "t3",
        tool: "run_tests",
        input: '{"suite": "auth"}',
        result: "FAILED: 1 of 24 — token_rotation_test",
        isError: true,
        status: "error",
      },
    ],
    status: "done",
  },
  {
    id: "a4",
    role: "assistant",
    content: "",
    status: "streaming",
  },
  {
    id: "a5",
    role: "assistant",
    content: "",
    status: "error",
  },
  {
    id: "u2",
    role: "user",
    content: "run analyze(target='auth', depth=2)",
    display: "runtime",
    status: "done",
  },
  {
    id: "r1",
    role: "assistant",
    content:
      "Analysis complete. 3 modules scanned, 1 warning:\n\n- `token_rotation_test` is flaky under concurrency.",
    display: "runtime",
    function: "analyze(target='auth', depth=2)",
    status: "done",
  },
];

export default function ChatPreviewPage() {
  const setMessages = useSessionStore((s) => s.setMessages);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setMessages(PREVIEW_SID, FIXTURES);
    setReady(true);
  }, [setMessages]);

  return (
    <div style={{ padding: "24px", maxWidth: 860, margin: "0 auto" }}>
      <h2 style={{ marginBottom: 16, color: "var(--text-bright)" }}>
        Message components preview
      </h2>
      <div
        style={{
          height: "70vh",
          overflow: "auto",
          border: "1px solid var(--border)",
          borderRadius: 12,
          background: "var(--bg-primary)",
        }}
      >
        {ready ? <MessageList sessionId={PREVIEW_SID} /> : null}
      </div>
    </div>
  );
}

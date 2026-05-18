"use client";

import { Suspense } from "react";
import { ChatView } from "@/components/chat/chat-view";

export default function NewChatPage() {
  return (
    <Suspense fallback={null}>
      <ChatView convId={null} />
    </Suspense>
  );
}

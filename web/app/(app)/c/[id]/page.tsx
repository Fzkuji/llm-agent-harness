"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { ChatView } from "@/components/chat/chat-view";

export default function ConvPage() {
  const params = useParams<{ id: string }>();
  const id = typeof params?.id === "string" ? params.id : null;
  return (
    <Suspense fallback={null}>
      <ChatView convId={id} />
    </Suspense>
  );
}

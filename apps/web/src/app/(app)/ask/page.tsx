import { AskChat } from "@/components/ask/ask-chat";

export const metadata = { title: "Ask · Trace Marketplace" };

export default function AskPage() {
  return (
    <div className="h-[calc(100vh-3.5rem-4rem)]">
      <AskChat />
    </div>
  );
}

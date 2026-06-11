import { createAgentUIStreamResponse, validateUIMessages } from "ai";
import { createClient } from "@/lib/supabase/server";
import { createAskAgent } from "@/lib/agent/ask-agent";

export const maxDuration = 120;

export async function POST(request: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }

  if (!process.env.OPENAI_API_KEY) {
    return Response.json(
      { error: "OPENAI_API_KEY is not configured; the code agent is unavailable." },
      { status: 503 },
    );
  }

  const { messages } = await request.json();

  return createAgentUIStreamResponse({
    agent: createAskAgent(),
    uiMessages: await validateUIMessages({ messages }),
  });
}

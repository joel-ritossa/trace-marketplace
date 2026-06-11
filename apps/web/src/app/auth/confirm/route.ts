import { NextResponse, type NextRequest } from "next/server";
import type { EmailOtpType } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase/server";

// Email-confirmation landing. The default GoTrue template links to
// /auth/v1/verify, which confirms the address and redirects here with a PKCE
// `code`; customized templates may link here directly with `token_hash`.
// Relative Location headers (not NextResponse.redirect) because request.url
// reflects the container-internal origin behind the ALB; the browser resolves
// these against the public origin it is already on.
function redirect(to: string) {
  return new NextResponse(null, { status: 303, headers: { Location: to } });
}

export async function GET(request: NextRequest) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const tokenHash = url.searchParams.get("token_hash");
  const type = url.searchParams.get("type") as EmailOtpType | null;
  const supabase = await createClient();

  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return redirect("/");
  } else if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });
    if (!error) return redirect("/");
  }

  // The address may already be confirmed even when the session handshake
  // fails (e.g. link opened in a different browser) — signing in resolves it.
  return redirect("/auth/sign-in?confirm=retry");
}

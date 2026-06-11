import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { AccountMenu } from "@/components/shell/account-menu";
import { NavLinks } from "@/components/shell/nav-links";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/auth/sign-in");
  }

  return (
    <div className="flex min-h-screen flex-col bg-canvas-soft">
      <header className="flex h-16 items-center justify-between border-b bg-background px-6">
        <div className="flex items-center gap-6">
          <span className="text-sm font-semibold tracking-tight">Trace Marketplace</span>
          <NavLinks />
        </div>
        <div className="flex items-center gap-4">
          <AccountMenu email={user.email ?? "?"} />
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">{children}</main>
    </div>
  );
}

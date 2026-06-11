import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { Sidebar } from "@/components/shell/sidebar";
import { TopBar } from "@/components/shell/top-bar";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/auth/sign-in");
  }

  return (
    <div className="flex min-h-screen bg-canvas-soft">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar email={user.email ?? "?"} />
        {/* Pages opt into a measure (max-w-6xl lists, max-w-2xl settings);
            inspection surfaces get the full width by default. */}
        <main className="w-full flex-1 px-6 py-8">{children}</main>
      </div>
    </div>
  );
}

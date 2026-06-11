import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

// Signed-in users have no business on the auth pages; send them home.
export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (user) {
    redirect("/");
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-canvas-soft px-4">
      {children}
    </div>
  );
}

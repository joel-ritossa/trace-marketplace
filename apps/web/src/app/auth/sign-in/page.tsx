import { AuthForm } from "@/components/auth/auth-form";

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ confirm?: string }>;
}) {
  const { confirm } = await searchParams;
  const notice =
    confirm === "retry"
      ? "We couldn't sign you in from that confirmation link. Sign in with your password — if the link already confirmed your email, it will work."
      : undefined;
  return <AuthForm mode="sign-in" notice={notice} />;
}

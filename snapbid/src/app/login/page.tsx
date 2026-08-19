import { LoginForm } from "./LoginForm";
import { AuthShell } from "@/components/AuthShell";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;
  return (
    <AuthShell title="Welcome back" subtitle="Sign in to quote the job.">
      <LoginForm next={next ?? "/dashboard"} />
    </AuthShell>
  );
}

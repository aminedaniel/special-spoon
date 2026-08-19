import { SignupForm } from "./SignupForm";
import { AuthShell } from "@/components/AuthShell";

export default function SignupPage() {
  return (
    <AuthShell
      title="Start quoting in minutes"
      subtitle="Sign one job in your first 14 days or your first month is free."
    >
      <SignupForm />
    </AuthShell>
  );
}

import { redirect } from "next/navigation";
import { getSession } from "@/lib/db/session";

export default async function Home() {
  const session = await getSession();
  if (!session) redirect("/login");
  redirect(session.org.onboarding_completed_at ? "/dashboard" : "/onboarding");
}

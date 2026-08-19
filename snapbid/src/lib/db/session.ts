import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import type { AppUser, Organization } from "@/lib/types";

export interface SessionContext {
  userId: string;
  email: string;
  profile: AppUser;
  org: Organization;
}

/** Current signed-in context, or null when signed out / not provisioned. */
export async function getSession(): Promise<SessionContext | null> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return null;

  const { data, error } = await supabase
    .from("users")
    .select("*, organizations(*)")
    .eq("id", user.id)
    .maybeSingle();

  if (error || !data) return null;
  const { organizations, ...profile } = data as AppUser & {
    organizations: Organization | Organization[] | null;
  };
  const org = Array.isArray(organizations) ? organizations[0] : organizations;
  if (!org) return null;

  return {
    userId: user.id,
    email: user.email ?? profile.email,
    profile: profile as AppUser,
    org,
  };
}

/** Same, but bounces to /login (and to onboarding until it is finished). */
export async function requireSession(options?: { allowOnboarding?: boolean }): Promise<SessionContext> {
  const session = await getSession();
  if (!session) redirect("/login");
  if (!options?.allowOnboarding && !session.org.onboarding_completed_at) redirect("/onboarding");
  return session;
}

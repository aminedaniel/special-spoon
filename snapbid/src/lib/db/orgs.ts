import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import type { Organization } from "@/lib/types";

export type OrgPatch = Partial<
  Pick<
    Organization,
    | "name"
    | "trade"
    | "logo_url"
    | "brand_color"
    | "phone"
    | "email"
    | "address"
    | "default_tax_rate"
    | "default_terms"
    | "default_deposit_percent"
    | "onboarding_completed_at"
    | "stripe_customer_id"
    | "stripe_subscription_id"
    | "stripe_connect_account_id"
    | "guarantee_started_at"
    | "guarantee_met_at"
    | "guarantee_status"
    | "billing_starts_at"
    | "guarantee_extended_at"
  >
>;

export async function updateOrg(orgId: string, patch: OrgPatch): Promise<Organization> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("organizations")
    .update(patch)
    .eq("id", orgId)
    .select()
    .single();
  if (error) throw new Error(`Could not update organization: ${error.message}`);
  return data as Organization;
}

/** For webhook/cron paths that have no user session. */
export async function updateOrgAsAdmin(orgId: string, patch: OrgPatch): Promise<Organization> {
  const admin = createAdminClient();
  const { data, error } = await admin
    .from("organizations")
    .update(patch)
    .eq("id", orgId)
    .select()
    .single();
  if (error) throw new Error(`Could not update organization: ${error.message}`);
  return data as Organization;
}

export async function getOrgAsAdmin(orgId: string): Promise<Organization | null> {
  const admin = createAdminClient();
  const { data } = await admin.from("organizations").select("*").eq("id", orgId).maybeSingle();
  return (data as Organization) ?? null;
}

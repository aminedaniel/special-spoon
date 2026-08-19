import { createClient } from "@supabase/supabase-js";
import { supabaseServiceKey, supabaseUrl } from "@/lib/env";

/**
 * Service-role client. Bypasses RLS, so it is only for paths that have no user
 * session and must scope themselves: signup provisioning, the public proposal
 * page (token lookup), Stripe webhooks, and the guarantee cron.
 *
 * Never import this from a Client Component.
 */
export function createAdminClient() {
  return createClient(supabaseUrl(), supabaseServiceKey(), {
    auth: { autoRefreshToken: false, persistSession: false },
  });
}

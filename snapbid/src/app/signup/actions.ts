"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import type { AuthFormState } from "@/app/login/actions";

const schema = z.object({
  business_name: z.string().trim().min(2, "Tell us your business name."),
  full_name: z.string().trim().min(2, "Tell us your name."),
  email: z.string().trim().email("Enter a valid email address."),
  password: z.string().min(8, "Password must be at least 8 characters."),
});

/**
 * Creates the auth user, then provisions the org + profile with the service
 * role. Provisioning has to happen here (not in a DB trigger) so a failure is
 * visible to the person signing up instead of leaving an orphaned auth user.
 */
export async function signupAction(_prev: AuthFormState, formData: FormData): Promise<AuthFormState> {
  const parsed = schema.safeParse({
    business_name: formData.get("business_name"),
    full_name: formData.get("full_name"),
    email: formData.get("email"),
    password: formData.get("password"),
  });
  if (!parsed.success) return { error: parsed.error.issues[0].message };

  const { business_name, full_name, email, password } = parsed.data;
  const supabase = await createClient();

  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: { data: { full_name, business_name } },
  });
  if (error || !data.user) {
    return { error: error?.message ?? "Could not create the account." };
  }

  const admin = createAdminClient();

  // A repeated signup for an existing confirmed email comes back with a user
  // that already has a profile — send them to sign in rather than re-provision.
  const { data: existingProfile } = await admin
    .from("users")
    .select("id")
    .eq("id", data.user.id)
    .maybeSingle();

  if (!existingProfile) {
    const { data: org, error: orgError } = await admin
      .from("organizations")
      // `trade` is NOT NULL and the real choice is the first step of
      // onboarding, which overwrites this placeholder.
      .insert({ name: business_name, trade: "roofing", email })
      .select("id")
      .single();
    if (orgError || !org) return { error: "Could not set up your workspace. Try again." };

    const { error: profileError } = await admin.from("users").insert({
      id: data.user.id,
      org_id: (org as { id: string }).id,
      email,
      full_name,
      role: "owner",
    });
    if (profileError) {
      await admin.from("organizations").delete().eq("id", (org as { id: string }).id);
      return { error: "Could not set up your workspace. Try again." };
    }
  }

  if (!data.session) {
    return {
      notice: "Check your email to confirm your address, then sign in to finish setup.",
    };
  }

  redirect("/onboarding");
}

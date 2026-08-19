"use server";

import { redirect } from "next/navigation";
import { z } from "zod";
import { getSession } from "@/lib/db/session";
import { createClient } from "@/lib/supabase/server";
import { updateOrg } from "@/lib/db/orgs";
import { countPriceBookItems, seedPriceBookFromTemplate } from "@/lib/db/price-book";
import { DEFAULT_TERMS } from "@/lib/seed/price-books";
import { startGuarantee } from "@/lib/guarantee";
import { percentToRate } from "@/lib/money";
import { createSubscriptionCheckout, isStripeConfigured } from "@/lib/stripe";
import { appUrl } from "@/lib/env";

export interface OnboardingState {
  error?: string;
}

const schema = z.object({
  trade: z.enum(["roofing", "remodeling"]),
  name: z.string().trim().min(2, "Tell us your business name."),
  phone: z.string().trim().max(40).optional().or(z.literal("")),
  email: z.string().trim().email("Enter a valid business email.").optional().or(z.literal("")),
  address: z.string().trim().max(200).optional().or(z.literal("")),
  brand_color: z.string().regex(/^#[0-9a-fA-F]{6}$/, "Pick a brand color."),
  default_tax_rate: z.string().optional(),
  default_deposit_percent: z.string().optional(),
});

const MAX_LOGO_BYTES = 2 * 1024 * 1024;

export async function completeOnboarding(
  _prev: OnboardingState,
  formData: FormData,
): Promise<OnboardingState> {
  const session = await getSession();
  if (!session) redirect("/login");

  const parsed = schema.safeParse({
    trade: formData.get("trade"),
    name: formData.get("name"),
    phone: formData.get("phone") ?? "",
    email: formData.get("email") ?? "",
    address: formData.get("address") ?? "",
    brand_color: formData.get("brand_color"),
    default_tax_rate: formData.get("default_tax_rate") ?? "0",
    default_deposit_percent: formData.get("default_deposit_percent") ?? "25",
  });
  if (!parsed.success) return { error: parsed.error.issues[0].message };

  const taxRate = percentToRate(parsed.data.default_tax_rate || "0");
  if (taxRate === null) return { error: "Sales tax must be a percentage between 0 and 100." };

  const depositPercent = Number(parsed.data.default_deposit_percent || "25");
  if (!Number.isFinite(depositPercent) || depositPercent < 0 || depositPercent > 100) {
    return { error: "Deposit must be a percentage between 0 and 100." };
  }

  // Logo (optional) goes to the public `branding` bucket under the org folder.
  let logoUrl: string | null = session.org.logo_url;
  const logo = formData.get("logo");
  if (logo instanceof File && logo.size > 0) {
    if (logo.size > MAX_LOGO_BYTES) return { error: "Logo must be under 2 MB." };
    if (!/^image\/(png|jpeg|webp|svg\+xml)$/.test(logo.type)) {
      return { error: "Logo must be a PNG, JPG, WEBP, or SVG file." };
    }
    const supabase = await createClient();
    const extension = logo.name.split(".").pop()?.toLowerCase() ?? "png";
    const path = `${session.org.id}/logo-${Date.now()}.${extension}`;
    const { error: uploadError } = await supabase.storage
      .from("branding")
      .upload(path, logo, { upsert: true, contentType: logo.type });
    if (uploadError) return { error: `Could not upload the logo: ${uploadError.message}` };
    const { data } = supabase.storage.from("branding").getPublicUrl(path);
    logoUrl = data.publicUrl;
  }

  // Seed the trade price book once — re-running onboarding must not duplicate it.
  const existingItems = await countPriceBookItems(session.org.id);
  if (existingItems === 0) {
    await seedPriceBookFromTemplate(session.org.id, parsed.data.trade);
  }

  const now = new Date();
  const alreadyStarted = Boolean(session.org.guarantee_started_at);

  await updateOrg(session.org.id, {
    trade: parsed.data.trade,
    name: parsed.data.name,
    phone: parsed.data.phone || null,
    email: parsed.data.email || null,
    address: parsed.data.address || null,
    brand_color: parsed.data.brand_color,
    logo_url: logoUrl,
    default_tax_rate: taxRate,
    default_deposit_percent: depositPercent,
    default_terms: session.org.default_terms ?? DEFAULT_TERMS[parsed.data.trade],
    onboarding_completed_at: session.org.onboarding_completed_at ?? now.toISOString(),
    ...(alreadyStarted ? {} : startGuarantee(now)),
  });

  redirect("/onboarding/billing");
}

/**
 * Card capture. The subscription is created with its trial ending at
 * `billing_starts_at`, so nothing is charged during the guarantee window.
 */
export async function startBillingCheckout(): Promise<{ error?: string }> {
  const session = await getSession();
  if (!session) redirect("/login");

  if (!isStripeConfigured()) {
    return { error: "Stripe is not configured on this deployment." };
  }
  if (session.org.stripe_subscription_id) redirect("/dashboard");

  let url: string;
  try {
    url = await createSubscriptionCheckout({
      orgId: session.org.id,
      email: session.org.email ?? session.email,
      billingStartsAt: session.org.billing_starts_at ?? new Date().toISOString(),
      existingCustomerId: session.org.stripe_customer_id,
      successUrl: `${appUrl()}/dashboard?billing=saved`,
      cancelUrl: `${appUrl()}/onboarding/billing?billing=cancelled`,
    });
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Could not start checkout." };
  }

  redirect(url);
}

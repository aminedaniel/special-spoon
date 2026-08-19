"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";
import { requireSession } from "@/lib/db/session";
import { updateOrg } from "@/lib/db/orgs";
import { createClient } from "@/lib/supabase/server";
import { percentToRate } from "@/lib/money";

export interface SettingsState {
  error?: string;
  notice?: string;
}

const schema = z.object({
  name: z.string().trim().min(2, "Tell us your business name."),
  phone: z.string().trim().max(40).optional().or(z.literal("")),
  email: z.string().trim().email("Enter a valid business email.").optional().or(z.literal("")),
  address: z.string().trim().max(200).optional().or(z.literal("")),
  brand_color: z.string().regex(/^#[0-9a-fA-F]{6}$/, "Pick a brand color."),
  default_terms: z.string().trim().max(4000).optional().or(z.literal("")),
});

export async function saveSettings(_prev: SettingsState, formData: FormData): Promise<SettingsState> {
  const session = await requireSession();
  const parsed = schema.safeParse({
    name: formData.get("name"),
    phone: formData.get("phone") ?? "",
    email: formData.get("email") ?? "",
    address: formData.get("address") ?? "",
    brand_color: formData.get("brand_color"),
    default_terms: formData.get("default_terms") ?? "",
  });
  if (!parsed.success) return { error: parsed.error.issues[0].message };

  const taxRate = percentToRate(String(formData.get("default_tax_rate") ?? "0"));
  if (taxRate === null) return { error: "Sales tax must be a percentage between 0 and 100." };

  const depositPercent = Number(formData.get("default_deposit_percent") ?? "25");
  if (!Number.isFinite(depositPercent) || depositPercent < 0 || depositPercent > 100) {
    return { error: "Deposit must be a percentage between 0 and 100." };
  }

  let logoUrl = session.org.logo_url;
  const logo = formData.get("logo");
  if (logo instanceof File && logo.size > 0) {
    if (logo.size > 2 * 1024 * 1024) return { error: "Logo must be under 2 MB." };
    const supabase = await createClient();
    const extension = logo.name.split(".").pop()?.toLowerCase() ?? "png";
    const path = `${session.org.id}/logo-${Date.now()}.${extension}`;
    const { error } = await supabase.storage
      .from("branding")
      .upload(path, logo, { upsert: true, contentType: logo.type });
    if (error) return { error: `Could not upload the logo: ${error.message}` };
    logoUrl = supabase.storage.from("branding").getPublicUrl(path).data.publicUrl;
  }

  try {
    await updateOrg(session.org.id, {
      name: parsed.data.name,
      phone: parsed.data.phone || null,
      email: parsed.data.email || null,
      address: parsed.data.address || null,
      brand_color: parsed.data.brand_color,
      default_terms: parsed.data.default_terms || null,
      default_tax_rate: taxRate,
      default_deposit_percent: depositPercent,
      logo_url: logoUrl,
    });
  } catch (error) {
    return { error: error instanceof Error ? error.message : "Could not save." };
  }

  revalidatePath("/settings");
  return { notice: "Saved." };
}

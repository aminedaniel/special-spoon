import type { GuaranteeStatus } from "./guarantee";

export type Trade = "roofing" | "remodeling";
export type UserRole = "owner" | "staff";
export type EstimateStatus = "draft" | "sent" | "viewed" | "signed" | "declined";
export type PaymentType = "deposit" | "subscription";
export type PaymentStatus = "pending" | "succeeded" | "failed" | "refunded";

export const TRADES: Trade[] = ["roofing", "remodeling"];

export const TRADE_LABELS: Record<Trade, string> = {
  roofing: "Roofing",
  remodeling: "Kitchen / bath / whole-home remodeling",
};

export interface Organization {
  id: string;
  name: string;
  trade: Trade;
  logo_url: string | null;
  brand_color: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  default_tax_rate: number;
  default_terms: string | null;
  default_deposit_percent: number;
  onboarding_completed_at: string | null;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  stripe_connect_account_id: string | null;
  guarantee_started_at: string | null;
  guarantee_met_at: string | null;
  guarantee_status: GuaranteeStatus;
  billing_starts_at: string | null;
  guarantee_extended_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AppUser {
  id: string;
  org_id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  created_at: string;
}

export interface PriceBookItem {
  id: string;
  org_id: string;
  name: string;
  description: string | null;
  category: string;
  unit: string;
  unit_price_cents: number;
  trade: Trade | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Lead {
  id: string;
  org_id: string;
  contact_name: string;
  email: string | null;
  phone: string | null;
  job_address: string | null;
  source: string | null;
  notes: string | null;
  created_at: string;
}

export interface Estimate {
  id: string;
  org_id: string;
  lead_id: string;
  title: string;
  status: EstimateStatus;
  subtotal_cents: number;
  tax_rate: number;
  tax_cents: number;
  total_cents: number;
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface EstimateLineItem {
  id: string;
  estimate_id: string;
  price_book_item_id: string | null;
  name: string;
  description: string | null;
  unit: string;
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
  position: number;
  /** Phase 2 seam — set by AI extraction, unused in Phase 1. */
  ai_confidence: number | null;
  needs_review: boolean;
  created_at: string;
}

export interface Proposal {
  id: string;
  org_id: string;
  estimate_id: string;
  public_token: string;
  cover_note: string | null;
  terms: string | null;
  deposit_amount_cents: number;
  sent_at: string | null;
  first_viewed_at: string | null;
  viewed_at: string | null;
  view_count: number;
  signed_at: string | null;
  signature_name: string | null;
  signature_ip: string | null;
  signature_user_agent: string | null;
  declined_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Payment {
  id: string;
  org_id: string;
  proposal_id: string | null;
  type: PaymentType;
  amount_cents: number;
  currency: string;
  status: PaymentStatus;
  stripe_ref: string | null;
  created_at: string;
  updated_at: string;
}

/** An estimate with everything needed to render it. */
export interface EstimateDetail extends Estimate {
  lead: Lead;
  line_items: EstimateLineItem[];
  proposal: Proposal | null;
}

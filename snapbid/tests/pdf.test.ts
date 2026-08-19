import { describe, expect, it } from "vitest";
import { PDFDocument } from "pdf-lib";
import { generateProposalPdf } from "@/lib/pdf";
import type { PublicProposal } from "@/lib/db/proposals";

const fixture: PublicProposal = {
  proposal: {
    id: "p1",
    public_token: "tok",
    cover_note: "Thanks for having us out, Dana.\n\nHere is exactly what we would do.",
    terms: "Pricing is valid for 30 days.\nDeposit due on acceptance.",
    deposit_amount_cents: 250000,
    sent_at: "2026-03-02T15:00:00Z",
    signed_at: null,
    signature_name: null,
    declined_at: null,
  },
  estimate: {
    id: "e1",
    title: "Roof replacement — 28 squares",
    subtotal_cents: 1_260_000,
    tax_rate: 0.0875,
    tax_cents: 110_250,
    total_cents: 1_370_250,
    notes: null,
    created_at: "2026-03-01T15:00:00Z",
  },
  lineItems: Array.from({ length: 30 }, (_, index) => ({
    id: `li${index}`,
    name: `Line item ${index + 1} with a name long enough to need wrapping across the column`,
    description: index % 3 === 0 ? "Includes labor, material, and haul-off of the old material." : null,
    unit: "square",
    quantity: 3.5,
    unit_price_cents: 12000,
    line_total_cents: 42000,
    position: index,
  })),
  lead: { contact_name: "Dana Whitfield", job_address: "812 Grove St, Austin TX", email: "dana@example.com" },
  org: {
    id: "o1",
    name: "Whitfield Roofing Co.",
    logo_url: null,
    brand_color: "#b91c1c",
    phone: "(512) 555-0134",
    email: "hello@example.com",
    address: "44 Trade Row, Austin TX",
    stripe_connect_account_id: null,
  },
};

describe("generateProposalPdf", () => {
  it("produces a multi-page PDF", async () => {
    const bytes = await generateProposalPdf(fixture);
    const header = Buffer.from(bytes.slice(0, 5)).toString("latin1");
    expect(header).toBe("%PDF-");
    expect(bytes.byteLength).toBeGreaterThan(2000);
    // 30 wrapped line items cannot fit on one page.
    const reloaded = await PDFDocument.load(bytes);
    expect(reloaded.getPageCount()).toBeGreaterThan(1);
  });

  it("renders a signed proposal without the signature lines", async () => {
    const signed: PublicProposal = {
      ...fixture,
      proposal: { ...fixture.proposal, signed_at: "2026-03-04T18:22:00Z", signature_name: "Dana Whitfield" },
      lineItems: fixture.lineItems.slice(0, 3),
    };
    const bytes = await generateProposalPdf(signed);
    expect(Buffer.from(bytes.slice(0, 5)).toString("latin1")).toBe("%PDF-");
  });

  it("handles an empty estimate without throwing", async () => {
    const empty: PublicProposal = {
      ...fixture,
      lineItems: [],
      proposal: { ...fixture.proposal, cover_note: null, terms: null, deposit_amount_cents: 0 },
      estimate: { ...fixture.estimate, subtotal_cents: 0, tax_cents: 0, total_cents: 0 },
    };
    const bytes = await generateProposalPdf(empty);
    expect(bytes.byteLength).toBeGreaterThan(500);
  });
});

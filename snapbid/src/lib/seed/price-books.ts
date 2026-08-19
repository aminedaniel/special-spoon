import type { Trade } from "@/lib/types";

/**
 * Trade price-book templates. A new org starts from the template for its trade
 * and edits the numbers to its own pricing — the AI (Phase 2) only ever
 * assembles from these rows, it never invents a price.
 *
 * Prices are illustrative national-ish midpoints in cents; every contractor is
 * expected to overwrite them during onboarding.
 */
export interface SeedItem {
  name: string;
  description?: string;
  category: string;
  unit: string;
  unit_price_cents: number;
}

const ROOFING: SeedItem[] = [
  { name: "Asphalt shingle roof — architectural", description: "Labor + material, per roofing square (100 sq ft)", category: "Roofing system", unit: "square", unit_price_cents: 45000 },
  { name: "Asphalt shingle roof — 3-tab", category: "Roofing system", unit: "square", unit_price_cents: 38000 },
  { name: "Standing seam metal roof", category: "Roofing system", unit: "square", unit_price_cents: 120000 },
  { name: "Tear-off — first layer", description: "Remove and dispose existing roofing", category: "Tear-off & disposal", unit: "square", unit_price_cents: 12000 },
  { name: "Tear-off — each additional layer", category: "Tear-off & disposal", unit: "square", unit_price_cents: 7500 },
  { name: "Dumpster / debris disposal", category: "Tear-off & disposal", unit: "ea", unit_price_cents: 55000 },
  { name: "Decking replacement — 1/2\" OSB", description: "Sheets replaced where rot is found", category: "Decking", unit: "sheet", unit_price_cents: 9500 },
  { name: "Fascia board replacement", category: "Decking", unit: "lf", unit_price_cents: 1400 },
  { name: "Synthetic underlayment", category: "Underlayment", unit: "square", unit_price_cents: 6500 },
  { name: "Ice & water shield", description: "Eaves, valleys, and penetrations", category: "Underlayment", unit: "square", unit_price_cents: 11000 },
  { name: "Drip edge", category: "Flashing & trim", unit: "lf", unit_price_cents: 450 },
  { name: "Valley flashing — metal", category: "Flashing & trim", unit: "lf", unit_price_cents: 1600 },
  { name: "Step flashing", category: "Flashing & trim", unit: "lf", unit_price_cents: 1200 },
  { name: "Chimney flashing kit", category: "Flashing & trim", unit: "ea", unit_price_cents: 65000 },
  { name: "Pipe boot / vent collar", category: "Flashing & trim", unit: "ea", unit_price_cents: 8500 },
  { name: "Ridge vent", category: "Ventilation", unit: "lf", unit_price_cents: 1800 },
  { name: "Static roof vent", category: "Ventilation", unit: "ea", unit_price_cents: 12000 },
  { name: "Soffit vent", category: "Ventilation", unit: "ea", unit_price_cents: 6500 },
  { name: "Ridge cap shingles", category: "Roofing system", unit: "lf", unit_price_cents: 1100 },
  { name: "Skylight — replace unit", category: "Skylights", unit: "ea", unit_price_cents: 145000 },
  { name: "Skylight — reflash only", category: "Skylights", unit: "ea", unit_price_cents: 48000 },
  { name: "Gutter — 5\" seamless aluminum", category: "Gutters", unit: "lf", unit_price_cents: 1200 },
  { name: "Downspout", category: "Gutters", unit: "lf", unit_price_cents: 1000 },
  { name: "Gutter guard", category: "Gutters", unit: "lf", unit_price_cents: 1500 },
  { name: "Steep-pitch surcharge (8/12+)", category: "Labor adjustments", unit: "square", unit_price_cents: 9000 },
  { name: "Two-story access surcharge", category: "Labor adjustments", unit: "square", unit_price_cents: 5000 },
  { name: "Permit & inspection", category: "Project costs", unit: "ea", unit_price_cents: 45000 },
  { name: "Roof repair — labor", category: "Repairs", unit: "hr", unit_price_cents: 12500 },
];

const REMODELING: SeedItem[] = [
  { name: "Demolition — kitchen", description: "Cabinets, counters, flooring; haul-off included", category: "Demolition", unit: "ea", unit_price_cents: 180000 },
  { name: "Demolition — bathroom", category: "Demolition", unit: "ea", unit_price_cents: 120000 },
  { name: "Demolition — general", category: "Demolition", unit: "hr", unit_price_cents: 8500 },
  { name: "Dumpster / debris disposal", category: "Demolition", unit: "ea", unit_price_cents: 62000 },
  { name: "Framing — labor", category: "Framing & structure", unit: "hr", unit_price_cents: 9500 },
  { name: "Header / load-bearing wall opening", category: "Framing & structure", unit: "ea", unit_price_cents: 285000 },
  { name: "Drywall — hang, tape, finish", category: "Drywall & paint", unit: "sf", unit_price_cents: 375 },
  { name: "Interior paint — walls & ceiling", category: "Drywall & paint", unit: "sf", unit_price_cents: 250 },
  { name: "Trim & baseboard install", category: "Drywall & paint", unit: "lf", unit_price_cents: 1200 },
  { name: "Electrical — rough-in per opening", category: "Electrical", unit: "ea", unit_price_cents: 22000 },
  { name: "Recessed light — supply & install", category: "Electrical", unit: "ea", unit_price_cents: 28000 },
  { name: "Panel / circuit upgrade", category: "Electrical", unit: "ea", unit_price_cents: 185000 },
  { name: "Plumbing — fixture rough-in & set", category: "Plumbing", unit: "ea", unit_price_cents: 95000 },
  { name: "Relocate drain / supply line", category: "Plumbing", unit: "ea", unit_price_cents: 145000 },
  { name: "HVAC — register / duct modification", category: "HVAC", unit: "ea", unit_price_cents: 68000 },
  { name: "Stock cabinetry — supply & install", category: "Cabinetry", unit: "lf", unit_price_cents: 32000 },
  { name: "Semi-custom cabinetry — supply & install", category: "Cabinetry", unit: "lf", unit_price_cents: 58000 },
  { name: "Custom cabinetry — supply & install", category: "Cabinetry", unit: "lf", unit_price_cents: 95000 },
  { name: "Cabinet hardware", category: "Cabinetry", unit: "ea", unit_price_cents: 2200 },
  { name: "Quartz countertop — fabricate & install", category: "Countertops", unit: "sf", unit_price_cents: 8500 },
  { name: "Granite countertop — fabricate & install", category: "Countertops", unit: "sf", unit_price_cents: 7500 },
  { name: "Laminate countertop", category: "Countertops", unit: "sf", unit_price_cents: 3200 },
  { name: "Undermount sink cutout", category: "Countertops", unit: "ea", unit_price_cents: 25000 },
  { name: "Tile backsplash", category: "Tile & flooring", unit: "sf", unit_price_cents: 2800 },
  { name: "Tile floor — supply & install", category: "Tile & flooring", unit: "sf", unit_price_cents: 3200 },
  { name: "Shower tile surround", category: "Tile & flooring", unit: "sf", unit_price_cents: 4200 },
  { name: "LVP flooring — supply & install", category: "Tile & flooring", unit: "sf", unit_price_cents: 1100 },
  { name: "Hardwood flooring — supply & install", category: "Tile & flooring", unit: "sf", unit_price_cents: 1450 },
  { name: "Shower pan / waterproofing", category: "Tile & flooring", unit: "ea", unit_price_cents: 145000 },
  { name: "Appliance install", category: "Fixtures & appliances", unit: "ea", unit_price_cents: 18000 },
  { name: "Vanity — supply & install", category: "Fixtures & appliances", unit: "ea", unit_price_cents: 125000 },
  { name: "Toilet — supply & install", category: "Fixtures & appliances", unit: "ea", unit_price_cents: 62000 },
  { name: "Faucet / fixture set", category: "Fixtures & appliances", unit: "ea", unit_price_cents: 42000 },
  { name: "Interior door — supply & install", category: "Doors & windows", unit: "ea", unit_price_cents: 55000 },
  { name: "Window — supply & install", category: "Doors & windows", unit: "ea", unit_price_cents: 118000 },
  { name: "Permit & inspection", category: "Project costs", unit: "ea", unit_price_cents: 85000 },
  { name: "Project management / supervision", category: "Project costs", unit: "day", unit_price_cents: 55000 },
  { name: "Final clean", category: "Project costs", unit: "ea", unit_price_cents: 45000 },
];

export const PRICE_BOOK_TEMPLATES: Record<Trade, SeedItem[]> = {
  roofing: ROOFING,
  remodeling: REMODELING,
};

export const DEFAULT_TERMS: Record<Trade, string> = {
  roofing: [
    "Pricing is valid for 30 days from the date of this proposal.",
    "A deposit is due on acceptance; the balance is due on completion.",
    "Decking replacement is billed per sheet actually replaced — rotten decking is not visible until tear-off.",
    "Work is warranted against defects in workmanship for 5 years. Manufacturer warranties pass through to the homeowner.",
    "Change orders must be approved in writing before the work is performed.",
  ].join("\n"),
  remodeling: [
    "Pricing is valid for 30 days from the date of this proposal.",
    "A deposit is due on acceptance; remaining draws are billed by phase as scheduled.",
    "Allowances for fixtures and finishes are noted per line item; selections above the allowance are billed as a change order.",
    "Concealed conditions (rot, non-code wiring, plumbing) discovered after demolition are billed as a change order.",
    "Work is warranted against defects in workmanship for 2 years.",
  ].join("\n"),
};

export const UNITS = ["ea", "hr", "day", "sf", "lf", "square", "sheet", "yd", "gal", "job"];

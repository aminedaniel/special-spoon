import { PDFDocument, StandardFonts, rgb, type PDFFont, type PDFPage } from "pdf-lib";
import { formatCents } from "@/lib/money";
import type { PublicProposal } from "@/lib/db/proposals";

const PAGE_WIDTH = 612; // US Letter, points
const PAGE_HEIGHT = 792;
const MARGIN = 48;
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2;

const INK = rgb(0.11, 0.13, 0.16);
const MUTED = rgb(0.42, 0.46, 0.52);
const RULE = rgb(0.85, 0.87, 0.9);

function hexToRgb(hex: string) {
  const match = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!match) return rgb(0.11, 0.29, 0.85);
  const int = parseInt(match[1], 16);
  return rgb(((int >> 16) & 255) / 255, ((int >> 8) & 255) / 255, (int & 255) / 255);
}

/** Greedy wrap on the real measured width of the font. */
function wrap(text: string, font: PDFFont, size: number, maxWidth: number): string[] {
  const lines: string[] = [];
  for (const paragraph of text.split("\n")) {
    if (paragraph.trim() === "") {
      lines.push("");
      continue;
    }
    let current = "";
    for (const word of paragraph.split(/\s+/)) {
      const candidate = current ? `${current} ${word}` : word;
      if (font.widthOfTextAtSize(candidate, size) <= maxWidth) {
        current = candidate;
      } else {
        if (current) lines.push(current);
        current = word;
      }
    }
    if (current) lines.push(current);
  }
  return lines;
}

function truncate(text: string, font: PDFFont, size: number, maxWidth: number): string {
  if (font.widthOfTextAtSize(text, size) <= maxWidth) return text;
  let result = text;
  while (result.length > 1 && font.widthOfTextAtSize(`${result}…`, size) > maxWidth) {
    result = result.slice(0, -1);
  }
  return `${result}…`;
}

export async function generateProposalPdf(data: PublicProposal): Promise<Uint8Array> {
  const { org, estimate, lineItems, lead, proposal } = data;

  const pdf = await PDFDocument.create();
  const regular = await pdf.embedFont(StandardFonts.Helvetica);
  const bold = await pdf.embedFont(StandardFonts.HelveticaBold);
  const brand = hexToRgb(org.brand_color ?? "#1d4ed8");

  pdf.setTitle(`${estimate.title} — ${org.name}`);
  pdf.setProducer("SnapBid");
  pdf.setCreator("SnapBid");

  let page: PDFPage = pdf.addPage([PAGE_WIDTH, PAGE_HEIGHT]);
  let y = PAGE_HEIGHT - MARGIN;

  const newPage = () => {
    page = pdf.addPage([PAGE_WIDTH, PAGE_HEIGHT]);
    y = PAGE_HEIGHT - MARGIN;
  };
  const ensure = (needed: number) => {
    if (y - needed < MARGIN + 24) newPage();
  };
  const text = (
    value: string,
    options: { x?: number; size?: number; font?: PDFFont; color?: ReturnType<typeof rgb> } = {},
  ) => {
    page.drawText(value, {
      x: options.x ?? MARGIN,
      y,
      size: options.size ?? 10,
      font: options.font ?? regular,
      color: options.color ?? INK,
    });
  };

  // --- header --------------------------------------------------------------
  page.drawRectangle({ x: 0, y: PAGE_HEIGHT - 8, width: PAGE_WIDTH, height: 8, color: brand });

  let logoHeight = 0;
  if (org.logo_url) {
    try {
      const response = await fetch(org.logo_url);
      if (response.ok) {
        const bytes = new Uint8Array(await response.arrayBuffer());
        const type = response.headers.get("content-type") ?? "";
        const image = type.includes("png")
          ? await pdf.embedPng(bytes)
          : await pdf.embedJpg(bytes);
        const scaled = image.scaleToFit(140, 48);
        page.drawImage(image, {
          x: MARGIN,
          y: y - scaled.height,
          width: scaled.width,
          height: scaled.height,
        });
        logoHeight = scaled.height + 10;
      }
    } catch {
      // A missing or unreadable logo must never block a proposal.
    }
  }
  y -= logoHeight;

  y -= 18;
  text(org.name, { size: 18, font: bold });
  y -= 14;
  const contactLine = [org.phone, org.email, org.address].filter(Boolean).join("  ·  ");
  if (contactLine) {
    text(truncate(contactLine, regular, 9, CONTENT_WIDTH), { size: 9, color: MUTED });
  }

  // Right-aligned proposal meta.
  const metaDate = new Date(proposal.sent_at ?? estimate.created_at).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  const metaLabel = "PROPOSAL";
  page.drawText(metaLabel, {
    x: PAGE_WIDTH - MARGIN - bold.widthOfTextAtSize(metaLabel, 11),
    y: y + 32,
    size: 11,
    font: bold,
    color: brand,
  });
  page.drawText(metaDate, {
    x: PAGE_WIDTH - MARGIN - regular.widthOfTextAtSize(metaDate, 9),
    y: y + 18,
    size: 9,
    font: regular,
    color: MUTED,
  });

  y -= 26;
  page.drawLine({
    start: { x: MARGIN, y },
    end: { x: PAGE_WIDTH - MARGIN, y },
    thickness: 1,
    color: RULE,
  });
  y -= 24;

  // --- customer ------------------------------------------------------------
  text("PREPARED FOR", { size: 8, font: bold, color: MUTED });
  y -= 14;
  text(lead.contact_name, { size: 12, font: bold });
  if (lead.job_address) {
    y -= 13;
    text(lead.job_address, { size: 10, color: MUTED });
  }
  y -= 24;
  text(estimate.title, { size: 14, font: bold });
  y -= 20;

  // --- cover note ----------------------------------------------------------
  if (proposal.cover_note) {
    for (const line of wrap(proposal.cover_note, regular, 10, CONTENT_WIDTH)) {
      ensure(14);
      text(line, { size: 10 });
      y -= 14;
    }
    y -= 10;
  }

  // --- line items ----------------------------------------------------------
  const columns = {
    name: MARGIN,
    qty: MARGIN + 300,
    unit: MARGIN + 358,
    price: MARGIN + 400,
    total: PAGE_WIDTH - MARGIN,
  };

  const drawTableHeader = () => {
    ensure(30);
    page.drawRectangle({
      x: MARGIN - 6,
      y: y - 6,
      width: CONTENT_WIDTH + 12,
      height: 20,
      color: rgb(0.96, 0.97, 0.98),
    });
    text("ITEM", { size: 8, font: bold, color: MUTED });
    page.drawText("QTY", { x: columns.qty, y, size: 8, font: bold, color: MUTED });
    page.drawText("UNIT", { x: columns.unit, y, size: 8, font: bold, color: MUTED });
    page.drawText("RATE", { x: columns.price, y, size: 8, font: bold, color: MUTED });
    const label = "AMOUNT";
    page.drawText(label, {
      x: columns.total - bold.widthOfTextAtSize(label, 8),
      y,
      size: 8,
      font: bold,
      color: MUTED,
    });
    y -= 20;
  };

  drawTableHeader();

  for (const item of lineItems) {
    const nameLines = wrap(item.name, regular, 10, 280);
    const descLines = item.description ? wrap(item.description, regular, 8.5, 280) : [];
    const blockHeight = nameLines.length * 13 + descLines.length * 11 + 8;

    if (y - blockHeight < MARGIN + 24) {
      newPage();
      drawTableHeader();
    }

    const rowTop = y;
    nameLines.forEach((line, index) => {
      page.drawText(line, { x: columns.name, y: y - index * 13, size: 10, font: regular, color: INK });
    });
    descLines.forEach((line, index) => {
      page.drawText(line, {
        x: columns.name,
        y: y - nameLines.length * 13 - index * 11 + 2,
        size: 8.5,
        font: regular,
        color: MUTED,
      });
    });

    const quantity = Number(item.quantity);
    const qtyLabel = Number.isInteger(quantity) ? String(quantity) : quantity.toFixed(2);
    page.drawText(qtyLabel, { x: columns.qty, y: rowTop, size: 10, font: regular, color: INK });
    page.drawText(item.unit, { x: columns.unit, y: rowTop, size: 10, font: regular, color: MUTED });
    page.drawText(formatCents(item.unit_price_cents), {
      x: columns.price,
      y: rowTop,
      size: 10,
      font: regular,
      color: INK,
    });
    const amount = formatCents(item.line_total_cents);
    page.drawText(amount, {
      x: columns.total - regular.widthOfTextAtSize(amount, 10),
      y: rowTop,
      size: 10,
      font: regular,
      color: INK,
    });

    y -= blockHeight;
    page.drawLine({
      start: { x: MARGIN, y: y + 6 },
      end: { x: PAGE_WIDTH - MARGIN, y: y + 6 },
      thickness: 0.5,
      color: RULE,
    });
  }

  // --- totals --------------------------------------------------------------
  ensure(90);
  y -= 10;

  const totalRow = (label: string, value: string, options: { emphasis?: boolean } = {}) => {
    const font = options.emphasis ? bold : regular;
    const size = options.emphasis ? 13 : 10;
    page.drawText(label, {
      x: columns.price - 40,
      y,
      size,
      font,
      color: options.emphasis ? INK : MUTED,
    });
    page.drawText(value, {
      x: columns.total - font.widthOfTextAtSize(value, size),
      y,
      size,
      font,
      color: options.emphasis ? brand : INK,
    });
    y -= options.emphasis ? 22 : 16;
  };

  totalRow("Subtotal", formatCents(estimate.subtotal_cents));
  if (estimate.tax_cents > 0) {
    totalRow(`Tax (${(Number(estimate.tax_rate) * 100).toFixed(2)}%)`, formatCents(estimate.tax_cents));
  }
  y -= 4;
  totalRow("Total", formatCents(estimate.total_cents), { emphasis: true });
  if (proposal.deposit_amount_cents > 0) {
    totalRow("Deposit due on acceptance", formatCents(proposal.deposit_amount_cents));
  }

  // --- terms ---------------------------------------------------------------
  if (proposal.terms) {
    ensure(60);
    y -= 12;
    text("TERMS", { size: 8, font: bold, color: MUTED });
    y -= 14;
    for (const line of wrap(proposal.terms, regular, 9, CONTENT_WIDTH)) {
      ensure(12);
      text(line, { size: 9, color: MUTED });
      y -= 12;
    }
  }

  // --- signature -----------------------------------------------------------
  ensure(70);
  y -= 18;
  page.drawLine({
    start: { x: MARGIN, y: y + 10 },
    end: { x: PAGE_WIDTH - MARGIN, y: y + 10 },
    thickness: 1,
    color: RULE,
  });
  y -= 8;

  if (proposal.signed_at) {
    text("ACCEPTED", { size: 8, font: bold, color: brand });
    y -= 14;
    text(`Signed by ${proposal.signature_name ?? lead.contact_name}`, { size: 10, font: bold });
    y -= 13;
    text(new Date(proposal.signed_at).toLocaleString("en-US"), { size: 9, color: MUTED });
  } else {
    text("To accept this proposal, open the link below and sign online.", { size: 9, color: MUTED });
    y -= 26;
    page.drawLine({
      start: { x: MARGIN, y },
      end: { x: MARGIN + 220, y },
      thickness: 0.75,
      color: RULE,
    });
    page.drawLine({
      start: { x: MARGIN + 260, y },
      end: { x: MARGIN + 380, y },
      thickness: 0.75,
      color: RULE,
    });
    y -= 12;
    text("Signature", { size: 8, color: MUTED });
    page.drawText("Date", { x: MARGIN + 260, y, size: 8, font: regular, color: MUTED });
  }

  // --- footer on every page ------------------------------------------------
  const pages = pdf.getPages();
  pages.forEach((current, index) => {
    const footer = `${org.name} · ${estimate.title} · page ${index + 1} of ${pages.length}`;
    current.drawText(truncate(footer, regular, 8, CONTENT_WIDTH), {
      x: MARGIN,
      y: 24,
      size: 8,
      font: regular,
      color: MUTED,
    });
  });

  return pdf.save();
}

# DESIGN.md: Pasaryo Frontend Direction

## 1. Design Read & Liveliness Dials (R-31, R-37)
**Reading this as:** Warm editorial marketplace & functional commerce utility (`Pasaryo`) -> dial **ENERGY 3 / RHYTHM 4 / MOTION 2**.

## 2. Purpose-Gate Decisions (R-31)
Every major visual and structural decision serves a concrete user need on a multi-step commerce platform:

- **Color Palette (Warm Cream, Charcoal Ink, Deep Terracotta):** Uses a warm alabaster canvas (`#FAF7F2`) with crisp white surfaces (`#FFFFFF`) and deep terracotta primary actions (`#A8381D`) to separate interactive purchase decisions from product metadata without cold SaaS blue-purple cliches.
- **Typography (Plus Jakarta Sans + JetBrains Mono):** Pairs humanist geometric UI copy (`Plus Jakarta Sans`) for Indonesian readability with tabular monospace (`JetBrains Mono`) for prices, order numbers, SKUs, promo codes, and stock counts so figures align vertically across cart and order summaries.
- **Layout & Rhythm (Asymmetric Two-Column Workspaces + Responsive Reflow):** Uses a persistent filter-and-catalog split on `/`, a sticky gallery + variant/purchase rail on `/produk/<id>/`, and a 65/35 items-to-summary split on `/keranjang/` and `/pesanan/<id>/` so users never lose sight of totals or actions while scrolling.
- **Spacing Scale (4px / 8px Base Grid):** Uses consistent `4px`, `8px`, `12px`, `16px`, `24px`, `32px`, `48px` increments so dense data views (address cards, order line items, tracking steps) breathe without wasted vertical scrolling.
- **Cards & Containers:** Uses cards strictly when grouping distinct actionable records (individual products, saved addresses, order records) with `1px solid #E4DDD0` borders rather than heavy drop shadows (`R-07`, `R-09`).
- **Icons & Visual Assets (R-23, R-05):** Uses clean typographic wordmark (`Pasaryo`), dynamic user initials for account badges, and database-driven product imagery with honest typographic fallback frames when a product has no uploaded image URL. No decorative filler icons, fake customer counters, or invented testimonials.

## 3. Verified Color Tokens (R-25)
All pairings verified via `contrast-check.py` (WCAG AA 4.5:1 normal text, 3.0:1 UI components):

| Token | Hex | Role | Contrast Verification |
| :--- | :--- | :--- | :--- |
| `--bg-canvas` | `#FAF7F2` | Main page background | Base canvas |
| `--bg-surface` | `#FFFFFF` | Cards, forms, modals, tables | Base elevated surface |
| `--bg-subtle` | `#F2ECE1` | Filter rails, secondary pills, summary headers | Base muted surface |
| `--text-primary` | `#1C1917` | Headings, product titles, prices | `16.37:1` on canvas, `17.49:1` on surface |
| `--text-secondary` | `#524B44` | Descriptions, address lines, specs | `8.03:1` on canvas, `8.58:1` on surface |
| `--text-muted` | `#5E554B` | Timestamps, SKU labels, helper text | `6.83:1` on canvas, `7.30:1` on surface |
| `--accent-primary` | `#A8381D` | Primary CTAs, active tabs, selected variants | `6.46:1` with `#FFFFFF`, `6.05:1` on canvas |
| `--accent-hover` | `#8C2D16` | Primary button hover & active state | `8.39:1` with `#FFFFFF` |
| `--accent-soft` | `#FCECE8` | Promo badges, active nav pill background | `7.32:1` with `#8C2D16` text |
| `--status-success-fg` / `--status-success-bg` | `#185C37` / `#E8F5EE` | Paid, completed, available stock, main address | `7.13:1` |
| `--status-warning-fg` / `--status-warning-bg` | `#7C4A03` / `#FEF3DE` | Pending payment, in-transit status | `6.73:1` |
| `--status-danger-fg` / `--status-danger-bg` | `#A82020` / `#FDECEC` | Cancelled, failed, out-of-stock, form errors | `6.36:1` (`7.26:1` solid `#A82020` with `#FFFFFF`) |
| `--border-subtle` | `#E4DDD0` | Structural section and card dividers | Structural divider |
| `--border-input` | `#756B60` | Interactive input, select, and checkbox borders | `5.21:1` on `#FFFFFF` |

## 4. Breakpoints & Mobile Reflow (R-03, antislop-layoutmobile)
- **Desktop (`> 1024px`):** Multi-column workspace grids (sidebar filter + 3-card product grid; 2-column cart/checkout/order detail).
- **Tablet (`640px` to `1024px`):** Stacked filter bar + 2-column product grid; stacked order summary below items.
- **Mobile (`< 640px`):** Single-column layout (`320px` safe), accessible collapsible mobile navigation menu (`aria-expanded`, `Escape` key support), `>= 44x44px` tap targets, zero horizontal page overflow.


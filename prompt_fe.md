# Stitch AI Frontend Design Prompts (Pasaryo E-Commerce)

> **How to use in Google Stitch AI:**
> - **Option A (Full App Generation):** Copy and paste **Section 1 (Master Prompt)** directly into Stitch AI to generate the complete design system and core screens.
> - **Option B (Screen-by-Screen Generation):** Paste the **Design System Foundation** from Section 1 together with any individual screen prompt from **Section 2** to generate or refine one screen at a time with maximum detail.

---

## Section 1: Master Prompt (Copy-Paste Ready for Stitch AI)

```text
Design a modern, professional, high-craft web e-commerce application named "Pasaryo" (a curated Indonesian marketplace). The interface must follow strict Anti-Slop UI craftsmanship rules: warm editorial utility, crystal-clear information hierarchy, honest data states, and zero generic AI cliches.

### 1. VISUAL DIRECTION & ANTI-SLOP UI RULES (MANDATORY)
- Aesthetic Persona: Warm Editorial Marketplace & Functional Commerce Utility (inspired by Aesop, Muji, and Stripe Checkout clarity).
- Light Mode Only (Warm Tactile Surfaces):
  - Canvas Background: #FAF7F2 (Warm Alabaster)
  - Elevated Surface (Cards, Panels, Modals, Header): #FFFFFF (Crisp Warm White)
  - Subtle Surface (Filter bars, summary headers, secondary pills): #F2ECE1 (Warm Sand)
  - Primary Text: #1C1917 (Deep Charcoal Ink, never pure #000000)
  - Secondary Text: #524B44 (Deep Umber Slate)
  - Muted Text: #5E554B (Warm Earth, maintaining >= 4.5:1 WCAG AA contrast)
  - Primary Accent (CTAs, active states, selected variants): #A8381D (Deep Terracotta) with #FFFFFF text
  - Primary Accent Hover: #8C2D16 (Roasted Terracotta)
  - Soft Accent Highlight: #FCECE8 background with #8C2D16 text
  - Semantic Status Tokens (WCAG AA verified):
    - Success (Paid, Completed, Available Stock, Main Address): #185C37 text on #E8F5EE background
    - Warning (Pending Payment, Shipped / In Transit): #7C4A03 text on #FEF3DE background
    - Danger (Cancelled, Failed, Expired, Out of Stock, Destructive actions): #A82020 text on #FDECEC background
  - Borders: 1px solid #E4DDD0 for cards/dividers; 1px solid #756B60 for form inputs, selects, and checkboxes (>= 3:1 contrast).
- Typography:
  - UI & Headings: "Plus Jakarta Sans" (weights 400, 500, 600, 700, 800), tight tracking (-0.02em) on headings, comfortable 1.6 line-height on body copy (max 65ch line width).
  - Numeric & Transactional Data: "JetBrains Mono" with `font-variant-numeric: tabular-nums` for all prices (Rp), discounts, SKUs, stock counts, postal codes, order numbers, timestamps, and fee breakdowns.
- Strict Anti-Slop Prohibitions:
  - NO purple/indigo/violet gradients, NO neon glows, NO glassmorphism blur clutter, NO 3D blobs or decorative floating shapes.
  - NO generic 3-equal-column SaaS feature marketing cards with decorative icons.
  - NO nested cards inside cards. Use 1px solid #E4DDD0 structural borders instead of heavy drop shadows.
  - NO fabricated social proof, fake star counters, fake "10,000+ happy customers" banners, or stock avatar photos. Use clean typographic wordmark ("Pasaryo") and 2-letter user initial badges (e.g., "BS").
  - NO vague button labels ("Submit", "Learn More", "Click Here", "Get Started"). Every button must state the exact verb + object (e.g., "Apply Filters", "Add to Cart", "Validate Promo Code", "Place Order Now").
  - Every form control (<input>, <select>, <textarea>) must have an explicit visible <label> above it and dedicated space for inline field-specific error messages.
  - Maintain at least 25% open canvas (#FAF7F2) around workspaces (1200px max container width, 4px/8px spacing scale).

### 2. GLOBAL NAVIGATION & SHELL
- Sticky Top Header (#FFFFFF with 1px bottom border #E4DDD0):
  - Left: Typographic wordmark "Pasaryo" with a small terracotta dot (#A8381D) and subtle tagline "Curated Daily Commerce".
  - Right Primary Navigation:
    1. "Product Catalog" (active state pill in #FCECE8)
    2. "Wishlist"
    3. "Shopping Cart" with live monospace item counter badge (e.g., "3")
    4. "My Orders"
    5. "Account" pill featuring a circular 2-letter initials avatar ("BS") and user full name (or "Sign In / Register" when logged out).
  - Mobile (< 640px): Collapses into an accessible "Navigation Menu" toggle button with minimum 44x44px tap targets.

### 3. CORE SCREENS & COMPLETE USER FEATURES TO INCLUDE

#### SCREEN 1: Product Catalog & Discovery Workspace
- Layout: Asymmetric 2-column workspace (280px sticky left filter panel + flexible right product area).
- Left Filter Panel:
  - Search input with visible label "Search Product Name"
  - Category select dropdown ("All Categories")
  - Brand select dropdown ("All Brands")
  - 2-column numeric input row for "Min Price (Rp)" and "Max Price (Rp)" in monospace
  - Text input for "Origin Shipping City" (e.g., Bandung, Jakarta)
  - Sort dropdown ("Newest", "Lowest Price", "Highest Price", "Name A to Z")
  - Full-width primary button "Apply Filters" and secondary button "Reset Filters".
- Right Product Area:
  - Top toolbar showing active result count in monospace ("Showing 12 of 48 products").
  - 3-column Product Card Grid (2 columns on tablet, 1 on mobile). Each Product Card contains strictly 3 data groups:
    1. Top 4:3 product image with top-left promo badge ("Save 15%") when discounted.
    2. Meta line ("Category · Brand · Origin City") + Product Title link.
    3. Final Price in bold tabular monospace ("Rp 185.000") + strikethrough original price ("Rp 215.000").
    - Card Footer Actions: Primary button "Select Variant" + secondary button "Save Wishlist".
  - Bottom pagination bar ("Page 1 of 4" with "Previous" and "Next" buttons).

#### SCREEN 2: Product Detail, Variant Selector, Specifications & Buyer Reviews
- Top Half (2-Column Split):
  - Left: 4:3 Primary Product Image + horizontal row of selectable thumbnail buttons (active thumbnail has 2px #A8381D border).
  - Right Purchase Panel:
    - Meta line ("Category / Brand / Shipped from Bandung") + H1 Product Title.
    - Active Promotion Callout Banner (#F2ECE1 surface with "15% Discount" badge and campaign title).
    - Large monospace Final Price ("Rp 185.000") + strikethrough original price.
    - Product description paragraph.
    - Color Variant Selector Pills (e.g., "Terracotta (14)", "Charcoal (6)", "Sand (0 - Out of Stock)") with selected state in #FCECE8 / 2px #A8381D border, plus live monospace helper text ("SKU: PSR-019-TRC | Available stock: 14 units").
    - Quantity Stepper (- / numeric input / +) paired with a semantic stock badge ("In Stock: 14").
    - Action Row: Primary button "Add to Cart" + Secondary button "Save to Wishlist".
- Bottom Half (2-Column Split):
  - Left Panel: "Technical Specifications & Shipping Info" formatted as a clean 2-column definition list (Category, Brand, Origin City, Material, Dimensions, Weight).
  - Right Panel: "Verified Buyer Reviews" with summary badge ("Rating 4.8/5 from 12 reviews") and chronological review records showing initials avatar, buyer name, rating badge ("5 / 5"), purchased variant name, date, and written review comment.

#### SCREEN 3: Shopping Cart, Promo Code Validation & Checkout Workspace
- Layout: 60/40 Asymmetric 2-Column Split.
- Left Column (Cart Items):
  - Inline Stock Alert Banner (#FDECEC danger surface) shown only when an item's quantity exceeds available variant stock.
  - List of Cart Item Records: Product title, Variant color & SKU in monospace, unit price, stock badge ("Stock: 8"), accessible quantity stepper (- / input / +), line total in bold monospace, and "Remove" danger button.
- Right Sticky Summary Rail (Shipping, Promo & Checkout):
  - Promo Code Validator: Input field ("Enter Promo Code", e.g., "HEMAT20") + "Validate Promo" button + active promo confirmation bar ("Code HEMAT20 applied: -Rp 35.000" with "Remove Promo" button).
  - Shipping Address Selector: Dropdown of saved user addresses ("Home (Main) - Budi Santoso, Bandung") with full street/subdistrict/city/province/postal code preview below and "Manage Addresses" link.
  - Shipping Method Radio Cards: Selectable cards showing courier name ("Reguler Nusantara", "Next Day Express"), estimated delivery days ("2-3 days"), and base cost in monospace ("Rp 18.000").
  - Payment Method Radio Cards: Selectable cards showing payment name ("Virtual Account BCA", "QRIS Instan"), provider channel, and service fee in monospace ("Fee: Rp 2.500").
  - Financial Breakdown Table: Subtotal, Shipping Fee, Payment Service Fee, Promo Discount (in green #185C37), and bold Total Payment in monospace.
  - Full-width Primary CTA: "Place Order Now".

#### SCREEN 4: Order Detail, Live Shipment Tracking, Re-Payment & Product Review
- Top Header Bar: Order Number in large monospace ("ORD-20261028-0042"), Order Status Badge ("Delivered" or "Completed" or "Pending Payment"),Creation Timestamp, Primary CTA "Confirm Order Received" (for Shipped/Delivered orders), and Danger CTA "Cancel Order" (for Pending Payment orders).
- Left Column:
  - Section A: "Ordered Items & Product Review". Lists each item with variant snapshot, SKU, quantity x unit price, and line total. When the order is "Completed", each item includes an inline "Write Product Review" sub-panel (Rating dropdown 1 to 5 + Written Review input + "Submit Product Review" button) or displays the buyer's submitted review badge.
  - Section B: "Shipment Tracking". Displays the immutable Shipping Address Snapshot box (Recipient name, phone, full address, estimated delivery date range), a "Refresh Tracking Status" button, and a vertical chronological timeline with green completed nodes (Status Code, Description, and Timestamp in monospace).
- Right Sticky Summary Rail:
  - Payment Status Card: Payment method name, status badge ("Pending" / "Paid" / "Expired"), payment reference code in monospace, and payment deadline timestamp. When unpaid or expired, includes a "Select Payment Method" dropdown and "Generate New Payment Invoice" button.
  - Order Cost Summary: Courier name, Subtotal, Shipping Fee, Service Fee, Discount, and Total Amount.

#### SCREEN 5: Account Settings, Authentication & Address Book CRUD
- Include both states:
  1. Guest Auth Card (centered 560px max-width): Accessible tab bar switching between "Sign In to Account" (Email, Password, "Sign In Now" CTA) and "Create New Account" (Full Name, Email, Password, Confirm Password, "Register My Account" CTA).
  2. Authenticated Member Workspace (60/40 2-Column Split):
     - Left Column: "Shipping Address Book" with "Add New Address" button, an inline collapsible Address Create/Edit Form (Label, Recipient Name, Recipient Phone 8-15 digits, 5-digit Postal Code, Street Address textarea, Subdistrict, City, Province, "Save Shipping Address" CTA), and saved Address Cards showing "Main Address" badge, "Set as Main", "Edit", and "Delete" buttons.
     - Right Column: "Profile Information" form (Initials avatar, Email read-only display, Full Name, Phone Number, Date of Birth, "Save Profile Changes" CTA) stacked above "Change Password" form (Current Password, New Password, Confirm New Password, "Update Password" CTA).
```

---

## Section 2: Modular Per-Screen Prompts (For Generating Screens Individually in Stitch AI)

If you want to generate or iterate on each screen one by one in Stitch AI, copy the **Style Prefix** below followed by the specific screen prompt.

### Style Prefix (Prepend to any individual screen prompt)
```text
Use a warm editorial e-commerce design system named "Pasaryo": #FAF7F2 warm alabaster canvas, #FFFFFF crisp surface cards with 1px solid #E4DDD0 borders, #F2ECE1 sand secondary bars, #1C1917 charcoal ink text, #524B44 secondary text, and #A8381D deep terracotta primary buttons with #FFFFFF text. Use "Plus Jakarta Sans" for UI text and "JetBrains Mono" (tabular-nums) for all prices, SKUs, order numbers, and quantities. No purple gradients, no glassmorphism, no nested cards, no fake social proof, and every input must have a visible label above it.
```

### Screen Prompt A: Catalog & Filter Workspace
```text
Design the Product Catalog & Discovery screen for "Pasaryo".
- Top sticky header with "Pasaryo" wordmark, navigation links ("Product Catalog" active, "Wishlist", "Shopping Cart (3)", "My Orders", "Account" with initials badge "FS").
- Main 2-column layout (280px left filter sidebar + 3-column right product grid).
- Left filter panel (#FFFFFF card, 1px solid #E4DDD0): "Search Product Name" input, "Category" select, "Brand" select, 2-column "Min Price (Rp)" and "Max Price (Rp)" monospace inputs, "Origin Shipping City" input, "Sort Products" select ("Newest", "Lowest Price", "Highest Price", "Name A to Z"), primary button "Apply Filters", and secondary button "Reset Filters".
- Right area: Top sand bar (#F2ECE1) showing "Showing 12 of 48 products", followed by a 3-column grid of clean product cards. Each card has a 4:3 product image with a top-left "Save 15%" badge, a metadata line ("Homeware · Kinto · Bandung"), bold product title, tabular monospace price ("Rp 245.000" with strikethrough "Rp 288.000"), and a bottom action row with "Select Variant" (#A8381D button) and "Save Wishlist" (outlined button). Include a bottom pagination bar ("Page 1 of 4", "Previous", "Next").
```

### Screen Prompt B: Product Detail, Variants, Specs & Reviews
```text
Design the Product Detail screen for "Pasaryo".
- Top back button "Back to Product Catalog".
- Upper 2-column workspace:
  - Left: 4:3 main product photo with a row of 4 selectable thumbnail previews below (active thumbnail has a 2px #A8381D border).
  - Right (#FFFFFF panel): Metadata breadcrumb ("Homeware / Kinto / Shipped from Bandung"), H1 product title, active promotion banner (#F2ECE1 box with "15% Off" badge and campaign name), large monospace price "Rp 245.000" + strikethrough "Rp 288.000", concise product description, "Select Color Variant" pill group ("Matte Black (12)" selected in #FCECE8 with 2px #A8381D border, "Warm Sand (5)", "Olive (0 - Out of Stock)" disabled), monospace SKU & stock line ("SKU: KNT-240-BLK | Available stock: 12 units"), quantity stepper (- / 1 / +) with green badge "In Stock (12)", primary CTA "Add to Cart", and secondary CTA "Save to Wishlist".
- Lower 2-column workspace:
  - Left (#FFFFFF panel): "Specifications & Shipping Information" 2-column definition list.
  - Right (#FFFFFF panel): "Verified Buyer Reviews" with badge "Rating 4.9/5 (8 reviews)" and review cards showing buyer initials avatar, buyer name, "5 / 5" badge, variant name, date, and honest review comment.
```

### Screen Prompt C: Shopping Cart, Promo Validation & Checkout
```text
Design the Shopping Cart & Checkout screen for "Pasaryo" using a 60/40 asymmetric 2-column layout.
- Left column ("Cart Items"):
  - An inline stock warning alert banner (#FDECEC background, #A82020 text) at the top explaining if any item exceeds available variant stock.
  - 3 Cart Item cards (#FFFFFF surface, 1px solid #E4DDD0): Product title, monospace variant & SKU ("Variant: Matte Black · SKU: KNT-240-BLK"), unit price "Rp 245.000 / unit", green badge "Stock: 12", quantity stepper (- / 2 / +), bold monospace line total "Rp 490.000", and danger button "Remove".
- Right sticky rail (#FFFFFF panel, "Shipping & Payment"):
  - Promo code section: Label "Promo Code", monospace input "HEMAT25", button "Validate Promo", and active applied banner ("Code HEMAT25 active: -Rp 25.000" with "Remove Promo" button).
  - "Shipping Address" dropdown ("Home (Main) - Ferdio, Bandung") with full street/subdistrict/city/province/postal code preview text and "Manage Addresses" link.
  - "Shipping Method" selectable radio cards ("Regular Courier - Est. 2-3 days - Rp 18.000" selected, "Express Next Day - Est. 1 day - Rp 32.000").
  - "Payment Method" selectable radio cards ("BCA Virtual Account - Fee: Rp 2.500" selected, "QRIS Instant - Fee: Rp 1.000").
  - Monospace financial summary rows (Subtotal, Shipping Fee, Service Fee, green Promo Discount, and bold Total Payment "Rp 485.500") + full-width primary CTA "Place Order Now".
```

### Screen Prompt D: Order Detail, Live Tracking, Re-Payment & Review Form
```text
Design the Order Detail, Shipment Tracking, and Product Review screen for "Pasaryo".
- Page Header: Monospace Order Number "ORD-20261028-0091", green status badge "Order Completed" (also show how "Confirm Order Received" primary button and "Cancel Order" danger button appear in the header), and creation date.
- 60/40 2-column split:
  - Left Column Top ("Items in This Order"): List of purchased items with variant, SKU, quantity x unit price, and line total. Below the first item, show an inline "Write Product Review" form (#F2ECE1 subtle box with "Product Rating (1 to 5)" dropdown, "Written Review" input, and "Submit Product Review" button). Below the second item, show a submitted review summary ("Your Review: Rating 5/5").
  - Left Column Bottom ("Shipment Tracking"): Header with "Refresh Tracking Status" button, immutable Shipping Address Snapshot box (Recipient name, phone, full address, estimated delivery dates), and a vertical chronological timeline with green completed dots ("DELIVERED", "IN_TRANSIT", "PROCESSING", "ORDER_CREATED") with descriptions and monospace timestamps.
  - Right Sticky Rail ("Billing & Payment Summary"): Payment info box showing payment method, status badge, reference number, and due date (plus a "Select Payment Method" dropdown and "Generate New Payment Invoice" button when payment is pending/expired), followed by the itemized monospace cost breakdown (Courier, Subtotal, Shipping Fee, Service Fee, Discount, Total Bill).
```

### Screen Prompt E: Account Profile, Security & Address Book CRUD
```text
Design the Account & Shipping Address Book screen for "Pasaryo" using a 60/40 2-column workspace (plus an inset preview of the Guest Sign In / Register tabbed card).
- Top header with page title "Account & Shipping Address Book" and danger button "Sign Out of Account".
- Left Column ("Shipping Address Book"):
  - Header with "Add New Address" primary button.
  - Expanded inline "Add / Edit Shipping Address" form (#F2ECE1 subtle panel) with labeled inputs: "Address Label" (Home/Office), "Recipient Name", "Recipient Phone" (with hint "8 to 15 digits, optional +"), "Postal Code (5 Digits)", "Street Address & Building Number" textarea, "Subdistrict", "City / Regency", "Province", and action buttons "Save Shipping Address" + "Cancel".
  - List of saved Address Cards (#FFFFFF): Address label ("Home"), green badge "Main Address", recipient name & monospace phone, full street/subdistrict/city/province/postal code, and action buttons "Set as Main", "Edit", and "Delete".
- Right Column:
  - Top Panel ("Profile Data"): Circular initials avatar "FS", email address in monospace, and labeled inputs for "Full Name", "Phone Number", "Date of Birth", and primary button "Save Profile Changes".
  - Bottom Panel ("Change Password"): Labeled inputs for "Current Password", "New Password", "Confirm New Password", and secondary button "Update Password".
```


# POLARIS Research Intelligence Platform -- UI/UX Design Brief

> **Document Class**: Design Specification, Standalone
> **Version**: 1.0.0
> **Created**: 2026-03-01
> **Purpose**: When given to a design-capable AI model (Claude, GPT, Gemini, etc.) with the instruction "Please create detailed Figma-ready wireframes/mockups for each screen described here", this document produces recognizable, consistent, and complete UI specifications for all 9 screens of the POLARIS dashboard.
> **Source**: Amendment A6 of the POLARIS Enterprise Product Transformation Plan (`proud-stargazing-lagoon.md`)

---

## Product Overview

POLARIS is an enterprise AI research platform that conducts autonomous deep research on any topic. It searches 1000+ sources, extracts evidence, verifies claims using NLI (Natural Language Inference), and produces publication-quality reports with full citation traceability. The system is built on an 8-node LangGraph pipeline: `plan -> search -> storm_interviews -> analyze -> verify -> evaluate -> synthesize + search_gaps`. Every piece of evidence is scored on 5 independent signals (Relevance, Authority, Density, Freshness, Grounding) and tiered (GOLD / SILVER / BRONZE). The pipeline self-corrects through iterative verification: verify finds gaps, search_gaps fills them, re-verify confirms.

The dashboard serves **TWO user personas**:

### Persona 1: Researcher (User Mode)

- **Role**: Subject matter expert, analyst, decision-maker
- **Goals**: Clear, digestible findings. Actionable insights. Trustworthy, verifiable conclusions.
- **Cares about**: Report quality, source credibility, citation accuracy, readability, export-ready deliverables
- **Does NOT care about**: Pipeline internals, token costs, model names, batch sizes, trace events, configuration values
- **Key workflows**: Type question -> watch progress -> read report -> explore evidence -> verify citations -> export PDF

### Persona 2: Pipeline Engineer (Operator Mode)

- **Role**: DevOps engineer, compliance officer, CISO, platform administrator
- **Goals**: Full pipeline visibility, debugging tools, performance metrics, audit trail access
- **Cares about**: Pipeline health, quality gates, cost efficiency, model performance, checkpoint state, error traces
- **Does NOT care about**: Report typography, reading experience (they have the Researcher view for that)
- **Key workflows**: Monitor pipeline execution -> inspect checkpoints -> review quality gates -> debug failures -> export audit trail

---

## Design System Requirements

### Theme

- **Dark mode**: Primary theme. Deep navy background with high-contrast text and accent colors.
- **Light mode**: Secondary theme. Clean white/gray with muted accents.
- **Toggle**: Header-level toggle switch. Transition: CSS custom property transition on `*` with `transition: background-color 200ms, color 200ms`.
- **Persistence**: Theme preference stored in `localStorage` and applied on page load before first paint (no flash of wrong theme).

### Typography

- **System font stack**: `Inter, -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif`
- **Report body**: Serif stack for readability: `Georgia, Cambria, 'Times New Roman', Times, serif`
- **Heading scale** (report view):
  - H1: 32px / 1.2 line-height / sans-serif / bold
  - H2: 24px / 1.3 / sans-serif / semibold
  - H3: 20px / 1.4 / sans-serif / medium
  - Body: 18px / 1.6 / serif / regular
  - Caption: 14px / 1.4 / sans-serif / regular
  - Badge text: 12px / 1.0 / sans-serif / semibold / uppercase / letter-spacing 0.5px
- **Monospace** (operator view, code, raw JSON): `'JetBrains Mono', 'Fira Code', 'SF Mono', 'Cascadia Code', Consolas, monospace`

### Color Palette

#### Dark Theme

| Token | Hex | Usage |
|-------|-----|-------|
| `--bg-primary` | `#0A1628` | Page background |
| `--bg-secondary` | `#0F1D32` | Card / panel background |
| `--bg-tertiary` | `#162440` | Elevated surfaces, modals |
| `--bg-hover` | `#1A2D50` | Hover state for cards/rows |
| `--text-primary` | `#E8ECF1` | Primary text |
| `--text-secondary` | `#8B9BB4` | Secondary / muted text |
| `--text-tertiary` | `#5A6B85` | Placeholder, disabled text |
| `--border-primary` | `#1E3255` | Card borders, dividers |
| `--border-active` | `#4A90D9` | Focused input borders |
| `--accent-primary` | `#4A90D9` | Primary buttons, links, active states |
| `--accent-primary-hover` | `#5BA0E9` | Button hover |
| `--accent-secondary` | `#2DD4BF` | Success indicators, verified badges |
| `--accent-warning` | `#F59E0B` | Warnings, partial states |
| `--accent-danger` | `#EF4444` | Errors, failures, cancel actions |
| `--tier-gold` | `#FFD700` | GOLD tier badge background |
| `--tier-gold-text` | `#1A1400` | GOLD tier badge text |
| `--tier-silver` | `#C0C0C0` | SILVER tier badge background |
| `--tier-silver-text` | `#1A1A1A` | SILVER tier badge text |
| `--tier-bronze` | `#CD7F32` | BRONZE tier badge background |
| `--tier-bronze-text` | `#1A0F00` | BRONZE tier badge text |
| `--faith-high` | `#22C55E` | Faithfulness >= 80% |
| `--faith-mid` | `#F59E0B` | Faithfulness 60-79% |
| `--faith-low` | `#EF4444` | Faithfulness < 60% |
| `--chart-1` | `#4A90D9` | Chart series 1 |
| `--chart-2` | `#2DD4BF` | Chart series 2 |
| `--chart-3` | `#F59E0B` | Chart series 3 |
| `--chart-4` | `#A78BFA` | Chart series 4 |
| `--chart-5` | `#F472B6` | Chart series 5 |

#### Light Theme

| Token | Hex | Usage |
|-------|-----|-------|
| `--bg-primary` | `#F8FAFC` | Page background |
| `--bg-secondary` | `#FFFFFF` | Card / panel background |
| `--bg-tertiary` | `#F1F5F9` | Elevated surfaces |
| `--bg-hover` | `#E2E8F0` | Hover state |
| `--text-primary` | `#0F172A` | Primary text |
| `--text-secondary` | `#475569` | Secondary text |
| `--text-tertiary` | `#94A3B8` | Placeholder, disabled |
| `--border-primary` | `#E2E8F0` | Borders, dividers |
| `--border-active` | `#3B82F6` | Focused input borders |
| `--accent-primary` | `#3B82F6` | Primary actions |

All other accent/tier/chart tokens remain identical across themes.

### Spacing Scale

Use an 8px base grid:
- `--space-1`: 4px (tight padding, badge internal)
- `--space-2`: 8px (element gap)
- `--space-3`: 12px (card internal padding)
- `--space-4`: 16px (section gap)
- `--space-5`: 24px (panel padding)
- `--space-6`: 32px (section separation)
- `--space-7`: 48px (major section gaps)
- `--space-8`: 64px (page-level spacing)

### Border Radius

- `--radius-sm`: 4px (badges, chips)
- `--radius-md`: 8px (cards, inputs)
- `--radius-lg`: 12px (panels, modals)
- `--radius-xl`: 16px (large cards, sections)
- `--radius-full`: 9999px (pills, circular buttons)

### Shadows (Dark Theme)

- `--shadow-sm`: `0 1px 2px rgba(0, 0, 0, 0.3)`
- `--shadow-md`: `0 4px 6px -1px rgba(0, 0, 0, 0.4), 0 2px 4px -2px rgba(0, 0, 0, 0.3)`
- `--shadow-lg`: `0 10px 15px -3px rgba(0, 0, 0, 0.5), 0 4px 6px -4px rgba(0, 0, 0, 0.4)`
- `--shadow-glow`: `0 0 20px rgba(74, 144, 217, 0.15)` (for active/focused elements)

### Responsive Breakpoints

- **Mobile**: 375px (phone)
- **Tablet**: 768px
- **Laptop**: 1024px
- **Desktop**: 1440px

Design mobile-first. All layouts start as single-column and progressively enhance at each breakpoint.

### Accessibility (WCAG 2.1 AA)

- All text meets 4.5:1 contrast ratio against its background (3:1 for large text >= 24px)
- All interactive elements are keyboard-navigable with visible `:focus-visible` outlines (`2px solid var(--accent-primary)`, `2px offset`)
- All buttons, links, and controls have ARIA labels
- All data visualizations include alt text and are not the sole means of conveying information
- Color-blind safe palettes for all data viz (never rely on color alone; use shapes, patterns, or labels)
- Skip-link as first focusable element: "Skip to main content"
- All form inputs have associated `<label>` elements
- Modal focus trapping: Tab cycles within modal when open
- Reduced motion: `@media (prefers-reduced-motion: reduce)` disables all animations

---

## Global Navigation

### Header Bar (Persistent Across All Screens)

- **Height**: 56px (desktop), 48px (mobile)
- **Background**: `var(--bg-secondary)` with 1px bottom border `var(--border-primary)`
- **Left**: POLARIS logo (wordmark, 24px height) + deployment mode badge ("Cloud" or "Sovereign" pill)
- **Center**: Tab navigation -- Landing | Report | Evidence | Mind Map | Memory | Pipeline Console
  - Active tab: `var(--accent-primary)` underline (2px) + bold text
  - Inactive tab: `var(--text-secondary)` + hover: `var(--text-primary)`
  - On mobile: horizontal scrollable tab bar with overflow indicators (gradient fade on edges)
- **Right**: View mode toggle ("Researcher" / "Operator" segmented control, 32px height) + Theme toggle (sun/moon icon) + User avatar/auth button
- **View mode toggle behavior**: Selecting "Researcher" hides all elements with class `.operator-only`. Selecting "Operator" shows them. Persisted to `localStorage`.

### Footer Bar (Optional, Operator Mode Only)

- **Height**: 32px
- **Content**: Pipeline version | Current LLM model | API status (green/yellow/red dot) | Cost this session | Uptime
- **Background**: `var(--bg-primary)` with top border

---

## Screen-by-Screen Specifications

### Screen 1: Landing / Research Input Screen

**URL Path**: `/` (default when no research is active)

**Layout**: Vertically centered content area. Max width 800px on desktop, 90% viewport width on mobile. Visually quiet -- draws attention to the search input as the primary call to action.

#### Elements

**1.1 Search Input Area**

- **Container**: Centered horizontally and positioned in the upper-third of the viewport (approximately 30% from top)
- **Input field**:
  - Width: 60% viewport on desktop (min 480px, max 720px), 90% on mobile
  - Height: 48px
  - Border: 1px `var(--border-primary)`, border-radius `var(--radius-lg)` (12px)
  - Background: `var(--bg-secondary)`
  - Placeholder text: "What do you want to research?" in `var(--text-tertiary)`, 16px
  - On focus: border transitions to `var(--border-active)`, subtle glow `var(--shadow-glow)`
  - Submit button: Integrated into the input field on the right side. Circular, 36px diameter, `var(--accent-primary)` background, white arrow icon (right-pointing). Hover: `var(--accent-primary-hover)`. Disabled state (empty input): 50% opacity, cursor not-allowed.
  - Keyboard: Enter key submits when input is non-empty

**1.2 Depth Selector Chips**

- **Position**: Directly below the search input, centered, 12px gap from input
- **Layout**: Horizontal row of 3 chips with 8px gap between them
- **Chip specs**:
  - Padding: 8px 16px
  - Border-radius: `var(--radius-full)` (pill shape)
  - Font: 14px sans-serif, medium weight
  - Unselected: `var(--bg-tertiary)` background, `var(--text-secondary)` text, 1px border `var(--border-primary)`
  - Selected: `var(--accent-primary)` background, white text, no border
- **Options**:
  - "Quick (5 min)" -- selected by default
  - "Standard (30 min)"
  - "Deep (90 min)"
- **Behavior**: Single-select. Clicking one deselects the others. Selection persisted to `localStorage`.

**1.3 Example Query Cards**

- **Position**: Below depth selector, 32px gap
- **Layout**: 2x2 grid on desktop (each card ~340px wide), single column on mobile (full width)
- **Grid gap**: 16px
- **Card specs**:
  - Background: `var(--bg-secondary)`
  - Border: 1px `var(--border-primary)`, border-radius `var(--radius-md)` (8px)
  - Padding: 16px
  - Hover: border transitions to `var(--accent-primary)` with 50% opacity, background to `var(--bg-hover)`, cursor pointer
  - Content:
    - Category icon (top-left, 20px, muted color): beaker (Science), scales (Policy), circuit (Technology), chart (Business)
    - Category label: 12px uppercase, `var(--text-tertiary)`, letter-spacing 1px
    - Query title: 15px, `var(--text-primary)`, semibold, 1-2 lines max
    - Description: 13px, `var(--text-secondary)`, 1 line, truncated with ellipsis
  - Click behavior: Populates search input with the query text, scrolls input into view on mobile
- **Example cards**:
  - Science: "What are the latest advances in CRISPR gene therapy for sickle cell disease?"
  - Policy: "How will the EU AI Act impact enterprise software companies starting August 2026?"
  - Technology: "Compare the performance of transformer vs. state-space models for long-context tasks"
  - Business: "What is the market opportunity for sovereign AI infrastructure in Canada?"

**1.4 Research History List**

- **Position**: Below example cards, 48px gap. Section heading: "Recent Research" (18px, semibold, `var(--text-primary)`) with "View All" link aligned right
- **Layout**: Vertical list of history cards, max 5 visible (scrollable if more). Full width within the 800px container.
- **Card specs**:
  - Background: `var(--bg-secondary)`
  - Border: 1px `var(--border-primary)`, border-radius `var(--radius-md)`
  - Padding: 12px 16px
  - Layout: Single row, space-between. Left: query text (16px, semibold, 1 line, truncate with ellipsis). Right: metadata badges.
  - Metadata badges (horizontal row, 8px gap):
    - Date: "2d ago" or "Mar 1" -- 12px, `var(--text-tertiary)`
    - Word count: pill badge, `var(--bg-tertiary)`, "12.4K words" -- 12px
    - Evidence count: pill badge, `var(--bg-tertiary)`, "1,011 ev" -- 12px
    - Faithfulness: pill badge, color-coded background:
      - >= 80%: `var(--faith-high)` bg with dark text
      - 60-79%: `var(--faith-mid)` bg with dark text
      - < 60%: `var(--faith-low)` bg with white text
      - Value: "80.5%"
  - Hover: background `var(--bg-hover)`, cursor pointer
  - Click: Navigates to Report View for that research session
  - Star/bookmark icon: Right side before metadata, toggles bookmark state

**1.5 "How It Works" Pipeline Diagram**

- **Position**: Below history list (or below example cards if no history), 48px gap
- **Layout**: Horizontal pipeline flow diagram, centered, max 720px wide
- **Design**: 7 connected steps in a horizontal flow with connecting lines/arrows
- **Steps** (left to right):
  1. "Plan" (clipboard icon)
  2. "Search" (magnifying glass icon)
  3. "Interview" (people icon)
  4. "Analyze" (chart icon)
  5. "Verify" (shield-check icon)
  6. "Synthesize" (document icon)
  7. "Report" (file-text icon)
- **Step node**: 40px circle, `var(--bg-tertiary)` background, icon in `var(--text-secondary)`, label below in 12px text
- **Connector**: 2px line in `var(--border-primary)` with small arrowhead at each connection
- **On mobile**: Horizontal scroll with snap points, or wrap to 2 rows (4 + 3)

---

### Screen 2: Active Research Screen (Pipeline Running)

**URL Path**: `/research/{vector_id}` (auto-navigates here when research starts)

**Layout**: Full viewport. Pipeline stepper across the top. Centered status area in the middle third. Live counters below. Activity log at the bottom (collapsible).

#### Elements

**2.1 Pipeline Stepper**

- **Position**: Full width, top of content area, below header. 64px height.
- **Layout**: 8 dots in a horizontal row, connected by lines. Centered within the viewport. Equal spacing.
- **Node states**:
  - Completed: `var(--accent-secondary)` (green) fill, white checkmark icon inside, brief pulse animation on completion
  - Active: `var(--accent-primary)` (blue) fill with pulsing animation (scale 1.0 -> 1.15 -> 1.0, 1.5s ease-in-out infinite), white activity icon inside
  - Pending: `var(--bg-tertiary)` fill, `var(--text-tertiary)` outline, no icon
  - Error: `var(--accent-danger)` fill, white X icon inside
- **Node size**: 32px diameter (desktop), 24px (mobile)
- **Connector line**: 2px, color matches the state of the left node (green if completed, blue if active-to-pending transition, gray if pending-to-pending)
- **Labels**: Below each node, 12px, `var(--text-secondary)`. Labels: Plan / Search / Interview / Analyze / Verify / Evaluate / Synthesize / Finalize
- **On mobile**: Horizontal scroll with current active node centered. Gradient fade on left/right edges to indicate scrollability.

**2.2 Status Center**

- **Position**: Centered vertically and horizontally in the main content area
- **Primary text**: Large (24px desktop, 20px mobile), `var(--text-primary)`, semibold. Dynamic text describing current activity:
  - "Planning research queries..."
  - "Searching 64 sources..."
  - "Interviewing 6 expert perspectives..."
  - "Analyzing 312 evidence pieces..."
  - "Verifying 89 claims against source text..."
  - "Evaluating quality gates..."
  - "Synthesizing final report..."
- **Animated ellipsis**: 3 dots after text, each fading in sequence (200ms delay between dots, 600ms cycle)
- **Progress bar**: Below status text, 16px gap
  - Width: 400px (desktop), 80% viewport (mobile)
  - Height: 6px
  - Background: `var(--bg-tertiary)`
  - Fill: Gradient from `var(--accent-primary)` to `var(--accent-secondary)` (left to right)
  - Border-radius: `var(--radius-full)`
  - Animation: Fill width tracks estimated progress (time-based, not step-based). Smooth transition 500ms.
- **Time estimate**: Below progress bar, 8px gap. "Estimated time remaining: ~12 min" in 14px, `var(--text-secondary)`. Updates every 30 seconds.

**2.3 Live Counters**

- **Position**: Below status center, 32px gap. Horizontal row of 3 counter cards.
- **Layout**: 3 cards in a row (desktop), 3 in a row stacked layout (mobile, narrower cards)
- **Counter card specs**:
  - Width: 160px (desktop), equal thirds on mobile
  - Background: `var(--bg-secondary)`, border 1px `var(--border-primary)`, border-radius `var(--radius-md)`
  - Padding: 16px, text centered
  - Icon: Top, 24px, `var(--accent-primary)`
  - Counter number: 28px, `var(--text-primary)`, bold, tabular-nums font-variant. Animated: number increments smoothly (counter animation, 300ms per digit change)
  - Label: 12px, `var(--text-secondary)`, below number
- **Counters**:
  - Magnifying glass icon + "{N}" + "Sources Found"
  - Document icon + "{N}" + "Evidence Extracted"
  - Shield-check icon + "{N}" + "Claims Verified"
- **Pulse animation**: When a counter increments, brief green pulse on the number (scale up 1.1x, green tint, 200ms)

**2.4 Cancel Button**

- **Position**: Bottom-right of the content area, 24px from edges
- **Style**: Outline button, `var(--accent-danger)` border and text, transparent background. Hover: `var(--accent-danger)` background with white text.
- **Text**: "Cancel Research"
- **Icon**: X circle, left of text
- **Behavior**: Click opens confirmation modal: "Are you sure you want to cancel? Progress will be lost." with "Cancel Research" (red, filled) and "Continue" (outline) buttons.

**2.5 Activity Log (Collapsible)**

- **Position**: Bottom of the viewport, collapsible panel
- **Toggle**: "Activity Log" text + chevron icon, 14px, `var(--text-secondary)`. Click toggles panel open/closed. Height animation 250ms ease.
- **Panel height** (expanded): 200px (desktop), 150px (mobile)
- **Content**: Scrollable list of pipeline events, newest at top
- **Event row**:
  - Timestamp: 11px monospace, `var(--text-tertiary)`, 60px width
  - Node badge: Colored pill (plan=purple, search=blue, interview=teal, analyze=orange, verify=green, evaluate=amber, synthesize=indigo, finalize=emerald), 10px font, uppercase
  - Description: 13px, `var(--text-primary)`, flex-grow
- **Max visible**: Scrollable, all events. Newest pinned to top unless user has scrolled.

---

### Screen 3: Report View

**URL Path**: `/report/{vector_id}`

**Layout**: Three-column layout on desktop (>= 1024px). TOC sidebar (left, 220px fixed) + Report body (center, max 720px reading width, flex-grow) + Source sidebar (right, 280px fixed, collapsible). On tablet: body + collapsible sidebar. On mobile: body only, TOC in hamburger menu.

#### Elements

**3.1 Quality Banner**

- **Position**: Full width of the report area, top, sticky below header (z-index above content, below modals)
- **Height**: 48px
- **Background**: `var(--bg-secondary)` with subtle bottom border
- **Content** (horizontal row, space-between):
  - Left: Overall grade badge -- letter grade (A/B/C/D/F) in a 32px circle
    - A (>= 90%): `var(--accent-secondary)` bg
    - B (>= 75%): `var(--accent-primary)` bg
    - C (>= 60%): `var(--accent-warning)` bg
    - D (< 60%): `var(--accent-danger)` bg
  - Center: Metric pills (horizontal row, 12px gap):
    - "Faithfulness: 80.5%" -- color-coded by threshold
    - "1,011 evidence" -- neutral pill
    - "18 sources" -- neutral pill
    - "3 iterations" -- neutral pill (`.operator-only`)
  - Right: Export buttons -- icon buttons (24px) with tooltips: PDF / Markdown / JSONL

**3.2 Table of Contents Sidebar (Desktop >= 1024px)**

- **Position**: Left sidebar, 220px width, sticky (top = header height + quality banner height)
- **Background**: `var(--bg-primary)` (same as page, blends in)
- **Content**: Ordered list of report section headings
- **Item specs**:
  - Font: 13px sans-serif, `var(--text-secondary)`
  - Padding: 8px 12px
  - Active section: `var(--accent-primary)` left border (3px), `var(--text-primary)` color, font-weight medium
  - Hover: `var(--bg-hover)` background
  - Click: Smooth scroll to section in report body, 80px offset for sticky header
- **Scroll behavior**: TOC highlights the section currently in viewport (intersection observer with 20% threshold)
- **On mobile**: Hidden. Accessible via hamburger menu icon in the header (overlay from left, 280px width, backdrop blur)

**3.3 Report Body**

- **Position**: Center column, max-width 720px, auto horizontal margins
- **Padding**: 32px (desktop), 16px (mobile)
- **Typography**:
  - Headings: sans-serif stack, `var(--text-primary)`
  - Body: serif stack, 18px / 1.6 line-height, `var(--text-primary)`
  - Paragraphs: 16px margin-bottom between paragraphs
  - Block quotes: Left border 3px `var(--accent-primary)`, padding-left 16px, `var(--text-secondary)` italic
- **Section structure**: Each section has:
  - Section heading (H2) with faithfulness badge inline
  - Faithfulness badge: Small pill to the right of heading text
    - >= 80%: green checkmark icon + "Verified" text
    - 60-79%: yellow warning icon + percentage
    - < 60%: red X icon + percentage
  - Section body: Paragraphs of prose
  - Inline citations: Superscript numbers `[1]`, `[2]`, etc. styled as links (`var(--accent-primary)` color, cursor pointer)

**3.4 Key Findings Summary Cards**

- **Position**: After the abstract paragraph, before Section 1. Full width of report body column.
- **Layout**: Horizontal scroll on mobile (snap to card), 2x3 or 3x2 grid on desktop (depending on count)
- **Card count**: 5-7 findings
- **Card specs**:
  - Width: 200px (fixed in scroll) or equal fractions in grid
  - Background: `var(--bg-secondary)`, border 1px `var(--border-primary)`, border-radius `var(--radius-md)`
  - Padding: 12px
  - Content:
    - Finding text: 14px, semibold, `var(--text-primary)`, 2-3 lines max, line-clamp
    - Bottom row: Evidence count badge + Confidence level (High/Medium/Low) + link to relevant section
  - Hover: `var(--shadow-md)` elevation, border `var(--accent-primary)` at 30% opacity
  - Click: Smooth-scrolls to the relevant report section

**3.5 Inline Smart Art (Mermaid Diagrams)**

- **Position**: Between paragraphs where the pipeline inserts them. Wrapped in a `<figure>` element.
- **Types**: Process flows, comparison matrices, causal chains, decision trees
- **Rendering**: Mermaid.js rendered to SVG, theme-aware (dark theme uses dark Mermaid config, light theme uses default)
- **Container**: Full width of report body, centered. Max-height 400px. Border-radius `var(--radius-md)`. Background `var(--bg-secondary)` with 16px padding.
- **Caption**: `<figcaption>` below diagram, 13px italic, `var(--text-secondary)`, centered
- **Alt text**: Every diagram has a descriptive `aria-label` summarizing its content
- **PDF export**: Diagrams rendered as inline SVG in the export HTML

**3.6 Citation Click Interaction**

- **Trigger**: Click on any superscript citation number `[N]`
- **Desktop (>= 1024px)**: Popover appears anchored to the citation. 400px wide, max-height 500px. Arrow pointing to citation.
- **Mobile (< 1024px)**: Bottom sheet slides up from bottom of viewport. Full width, max-height 70vh. Drag handle at top for dismiss.
- **Content** (3 tabs):
  - **Tab 1 "Source"**:
    - Mini-webpage preview in sandboxed iframe (200px height, full width)
    - Cited sentence highlighted in yellow within the preview
    - If iframe unavailable: fallback to blockquote display of the cited text
    - "View Original" link button below preview
  - **Tab 2 "Chain of Custody"**:
    - Visual chain displayed vertically:
      - Card A: "Finding" -- the claim in the report that cites this source. Blue left border.
      - Arrow down
      - Card B: "Citation" -- the specific citation reference. Teal left border.
      - Arrow down
      - Card C: "Source Sentence" -- the exact sentence from the source that supports the claim. Green left border.
      - Arrow down
      - Card D: "Reasoning" -- the NLI verification reasoning. Purple left border.
    - Each card: `var(--bg-tertiary)` background, 12px padding, 14px text, monospace for source quotes
  - **Tab 3 "Metadata"**:
    - Source title (16px, semibold, linked to URL)
    - URL (13px, `var(--accent-primary)`, truncated with full URL on hover tooltip)
    - Quality tier badge (GOLD/SILVER/BRONZE with tier colors)
    - Relevance score bar (horizontal bar chart, 0-1.0 scale, `var(--accent-primary)` fill)
    - Publication year
    - Author list (comma-separated, max 3 visible + "et al." truncation)
    - Verification verdict: SUPPORTED (green badge) / NOT_SUPPORTED (red badge) / NEUTRAL (gray badge)
- **Tab styling**: Horizontal tab bar at top of popover/sheet. Active tab: underline + bold. Inactive: `var(--text-secondary)`.
- **Close**: Click outside (desktop), swipe down (mobile), Escape key, or X button

**3.7 Source Cards Sidebar (Desktop >= 1024px)**

- **Position**: Right sidebar, 280px width. Sticky (same as TOC). Collapsible via toggle button.
- **On tablet/mobile**: Appears as a section below the report body with heading "Sources ({N})"
- **Card specs** (one per source):
  - Background: `var(--bg-secondary)`, border-left 3px colored by tier
  - Padding: 12px
  - Collapsed (default): Source title (14px, semibold, 1 line truncated) + tier badge + "Cited {N}x" badge
  - Expanded (click): Adds: trust score ring chart (40px, SVG donut), list of all evidence pieces from this source (each as a mini-card with quote snippet + citation number)
  - Trust score ring chart: SVG donut, `var(--accent-primary)` fill arc, percentage in center
- **Sort**: By citation count (most cited first) by default

**3.8 Export Buttons**

- **Behavior on click**:
  - PDF: Triggers `POST /api/research/export/{vector_id}` -> downloads PDF file. Button shows spinner while generating.
  - Markdown: Downloads `.md` file with full report, citations as footnotes, bibliography at end
  - JSONL: Downloads raw pipeline output as `.jsonl` (`.operator-only` -- hidden in Researcher mode)

---

### Screen 4: Evidence Browser

**URL Path**: `/evidence/{vector_id}`

**Layout**: Full width. Filter bar at top (sticky below header). Evidence cards in masonry grid below. Detail panel slides in from right on card click (overlay on mobile, inline panel on desktop).

#### Elements

**4.1 Filter Bar**

- **Position**: Full width, sticky below header. Height 56px. Background `var(--bg-secondary)` with bottom border.
- **Content** (horizontal row, items centered vertically):
  - **Tier filter chips**: 4 chips in a row: "All" / "Gold" / "Silver" / "Bronze"
    - Each: pill shape, 32px height, 12px horizontal padding
    - Active: filled with tier color (or `var(--accent-primary)` for "All"), white/dark text
    - Inactive: `var(--bg-tertiary)` background, `var(--text-secondary)` text
    - Multi-select: Click toggles chip on/off. "All" deselects others; selecting any tier deselects "All".
  - **Sort dropdown**: 140px width select element. Options: Relevance / Recency / Confidence / Citations / Authority / Tier
    - Styled as custom dropdown with chevron icon
  - **Search input**: Expandable. Icon-only by default (magnifying glass, 36px). Click expands to 200px input field. Searches evidence quotes and source titles.
  - **View toggle**: Two icon buttons -- grid view (default) / list view. Active: `var(--accent-primary)`, inactive: `var(--text-tertiary)`
- **Result count**: Right-aligned, "Showing {N} of {total} evidence" in 13px `var(--text-secondary)`

**4.2 Evidence Cards (Grid View)**

- **Layout**: Masonry grid. Desktop (>= 1440px): 3 columns. Tablet (768-1439px): 2 columns. Mobile (< 768px): 1 column. Gap: 16px.
- **Card specs**:
  - Background: `var(--bg-secondary)`, border 1px `var(--border-primary)`, border-radius `var(--radius-md)`
  - Padding: 16px
  - Top row: Tier badge (left) + relevance bar (right, 60px wide horizontal bar)
  - Quote snippet: 14px, `var(--text-primary)`, 2 lines max, line-clamp with ellipsis. Italic style.
  - Source title: 13px, `var(--text-secondary)`, 1 line, truncated
  - Bottom row: Citation count badge ("Cited 3x") + confidence score (percentage)
  - Hover: `var(--shadow-md)` elevation, border `var(--accent-primary)` at 30% opacity, tooltip shows full quote
  - Click: Opens detail panel
  - Keyboard: `tabindex="0"`, Enter/Space opens detail panel, `role="button"`, `aria-label` with source title
- **Loading animation**: Cards fade in staggered (50ms delay between cards, 200ms fade-in each)

**4.3 Evidence Cards (List View)**

- **Layout**: Full-width rows, no masonry
- **Row specs**:
  - Height: 64px
  - Horizontal layout: Tier badge (48px) | Quote snippet (flex-grow, 1 line) | Source title (200px) | Relevance bar (80px) | Citation count (60px) | Confidence (60px)
  - Alternating row backgrounds: `var(--bg-primary)` and `var(--bg-secondary)`
  - Hover: `var(--bg-hover)` background

**4.4 Detail Panel**

- **Desktop**: Slides in from right, 400px width, overlays content with backdrop. Close button (X) top-right.
- **Mobile**: Full-screen overlay, slide up from bottom
- **Content** (scrollable):
  - **Full quote**: 16px serif, `var(--text-primary)`, full evidence text with no truncation. Enclosed in styled blockquote.
  - **Source metadata card**: Source title (linked), URL, publication date, author list
  - **Verification result**: Verdict badge (SUPPORTED/NOT_SUPPORTED/NEUTRAL), NLI confidence score, reasoning text (13px, `var(--text-secondary)`)
  - **Report sections citing this evidence**: List of section titles with links, click navigates to Report View at that section
  - **5-Signal Radar Chart**:
    - SVG radar/spider chart, 200px diameter, centered
    - 5 axes: Relevance, Authority, Density, Freshness, Grounding
    - Each axis: 0.0 to 1.0 scale, labeled at the outer edge
    - Data polygon: `var(--accent-primary)` fill at 20% opacity, `var(--accent-primary)` stroke 2px
    - Grid rings: 3 concentric pentagons at 0.33, 0.66, 1.0 in `var(--border-primary)`
    - Dots: 6px circles at each data point, `var(--accent-primary)` fill
    - Accessible: `aria-label` describing all 5 values

**4.5 Evidence Graph (Toggle Modes)**

- **Position**: Toggled via a "Graph View" button in the filter bar (replaces masonry grid)
- **Canvas**: Full available width and height (viewport minus header and filter bar)
- **4 mode tabs** (horizontal, above canvas):
  - **Force-Directed**: Default. Nodes = evidence pieces, colored by source. Clusters form around sources. Node size = relevance score. Edge thickness = co-citation count. Physics simulation with charge repulsion + link attraction.
  - **Cross-Reference**: Nodes = sources. Edges connect sources that cite each other or corroborate the same finding. Edge label = corroboration count. Directed edges show citation direction.
  - **Timeline**: Horizontal axis = publication date. Vertical axis = relevance score. Each evidence piece is a dot (colored by tier). Hover shows details. Useful for seeing recency distribution.
  - **Mind Map**: Radial tree (see Screen 5 for full specification). Abbreviated version here: center = question, first ring = sections, second ring = key findings, outer ring = sources.
- **Controls**: Zoom (scroll/pinch), Pan (drag), Reset (button), Full-screen (button)

---

### Screen 5: Mind Map View

**URL Path**: `/mindmap/{vector_id}`

**Layout**: Full-canvas SVG/Canvas visualization filling the entire viewport below the header. Floating toolbar at top-right for controls. Floating filter panel at top-left (collapsible).

#### Elements

**5.1 Mind Map Canvas**

- **Rendering**: SVG (preferred for accessibility) or Canvas (for performance with > 500 nodes). Use D3.js force layout or custom radial tree layout.
- **Background**: `var(--bg-primary)` with subtle radial gradient (slightly lighter at center)

**5.2 Node Hierarchy**

- **Center node** (Research Question):
  - Shape: Circle, 80px diameter
  - Fill: `var(--accent-primary)`
  - Text: Research question text, 14px, white, centered, max 3 lines with ellipsis
  - Glow: `var(--shadow-glow)` with 30px spread
  - Fixed position: center of canvas

- **First ring** (Report Sections):
  - Shape: Circle, 48px diameter
  - Fill: `var(--bg-tertiary)` with 2px border colored by section faithfulness (green/yellow/red)
  - Text: Section title, 11px, `var(--text-primary)`, centered, max 2 lines
  - Position: Evenly distributed on a ring ~200px radius from center
  - Connection to center: Curved line, 2px, `var(--border-primary)`, subtle opacity

- **Second ring** (Key Findings):
  - Shape: Circle, 28px diameter
  - Fill: `var(--bg-secondary)` with 1px border `var(--border-primary)`
  - Text: None (tooltip on hover shows finding text)
  - Position: Clustered near their parent section, ~350px radius from center
  - Connection to section: Straight line, 1.5px, `var(--border-primary)`

- **Outer ring** (Sources):
  - Shape: Circle, 16px diameter
  - Fill: Colored by tier -- `var(--tier-gold)`, `var(--tier-silver)`, `var(--tier-bronze)`
  - Text: None (tooltip on hover shows source title)
  - Position: ~500px radius from center, clustered near findings they support
  - Connection to findings: Line, 1px thickness. Color = verification status:
    - SUPPORTED: `var(--accent-secondary)` (green)
    - NOT_SUPPORTED: `var(--accent-danger)` (red)
    - NEUTRAL: `var(--text-tertiary)` (gray)
  - Line thickness: Proportional to citation count (1px base + 0.5px per citation)

**5.3 Cross-Cutting Indicators**

- **Multi-section sources**: Sources cited in 2+ sections get a halo effect (2px ring, `var(--accent-primary)`, pulsing opacity 0.5 -> 1.0)
- **Multi-section findings**: Findings referenced in 2+ sections connected by dashed arcs (curved line, 1px dashed, `var(--accent-primary)` at 50% opacity)
- **High-value clusters**: When 3+ sources corroborate a finding, the finding node gets a subtle glow and increased size (32px)

**5.4 Interactions**

- **Click node**: Highlights all connections to/from that node. Dims everything else to 20% opacity. Shows info card anchored to node.
- **Info card** (on node click): Floating card, 240px wide
  - For center node: Question text, total evidence count, total sources
  - For section node: Section title, faithfulness %, evidence count, "View in Report" link
  - For finding node: Finding text, confidence, evidence count, source list
  - For source node: Title, URL (linked), tier badge, radar chart mini (120px), "View Evidence" link
- **Hover node**: Tooltip with summary text. Highlight direct connections only (not recursive).
- **Double-click source**: Opens mini-webpage preview modal (same as citation Tab 1 from Report View)
- **Scroll**: Zoom in/out (0.25x to 4.0x range)
- **Drag on canvas**: Pan
- **Drag on node**: Move the node (updates physics simulation if force-directed)

**5.5 Filter Toolbar**

- **Position**: Top-left, floating over canvas, collapsible
- **Background**: `var(--bg-secondary)` with `var(--shadow-lg)`, border-radius `var(--radius-lg)`
- **Controls**:
  - Tier toggles: 3 checkboxes with colored squares (Gold/Silver/Bronze). Unchecking hides those nodes.
  - Section filter: Dropdown multi-select. Filter to show only nodes from selected sections.
  - Verification filter: 3 checkboxes (Supported/Not Supported/Neutral). Filters connections by color.
  - Search: Text input. Matching nodes pulse and center in viewport.
  - "Reset View" button: Returns to default zoom and center position

**5.6 Control Toolbar**

- **Position**: Top-right, floating over canvas
- **Buttons** (vertical stack, icon-only with tooltips):
  - Zoom in (+)
  - Zoom out (-)
  - Fit to screen
  - Full-screen toggle
  - Screenshot (exports canvas as PNG)
  - Layout toggle: Switch between radial tree and force-directed layouts

---

### Screen 6: Operator / Pipeline Console View

**URL Path**: `/console/{vector_id}` (`.operator-only` -- hidden when in Researcher mode)

**Layout**: Split panel. Left panel (360px fixed) for pipeline metrics. Right panel (flex-grow) for tabbed content (Reasoning Stream / Activity Log / Checkpoint Timeline). On tablet: stacked vertically. On mobile: tabbed single-panel.

#### Elements

**6.1 Pipeline Metrics Panel (Left)**

- **Background**: `var(--bg-secondary)`, right border 1px `var(--border-primary)`
- **Padding**: 24px
- **Sections** (vertical stack, 24px gap):

  - **Status Badge**: Full width, centered. Large pill: "Running" (blue, pulsing) / "Complete" (green) / "Error" (red) / "Cancelled" (gray). 14px text, 40px height.

  - **Pipeline Stepper** (compact version): Same 8 nodes as Active Research stepper, but smaller (20px nodes) and always visible. Horizontal, wrapping to 2 rows if needed.

  - **Metrics Grid**: 2-column grid of metric cards, 8px gap
    - Each card: `var(--bg-tertiary)` background, 8px padding, border-radius `var(--radius-sm)`
    - Label: 11px uppercase, `var(--text-tertiary)`, letter-spacing 0.5px
    - Value: 20px bold, `var(--text-primary)`
    - Cards:
      - Faithfulness %
      - Evidence count
      - Source count
      - Word count
      - Iteration #
      - Cost ($X.XX)
      - Duration (Xm Xs)
      - Model name (truncated)

  - **Quality Gates**: Row of 6 indicator dots, each 12px diameter, with label below (10px)
    - Gates: evidence_count, faithfulness, word_count, citation_count, source_count, off_topic
    - States: Green (pass) / Red (fail) / Gray (pending) / Yellow (warning)
    - Tooltip on hover: "{gate_name}: {value} vs threshold {threshold}"

  - **Cost Breakdown** (collapsible):
    - Heading: "Cost Breakdown" with chevron toggle
    - Content: Bar chart (horizontal bars) showing cost per pipeline phase
    - Bars colored by phase (same colors as node badges in activity log)

**6.2 Checkpoint Timeline (AMENDMENT A2)**

- **Position**: First tab in right panel. Full width.
- **Layout**: Horizontal timeline with dots at each checkpoint, spanning full width
- **Timeline specs**:
  - Horizontal line: 2px, `var(--border-primary)`, centered vertically
  - Checkpoint dots: 12px diameter, on the timeline line, spaced proportionally by timestamp
  - Dot fill: `var(--accent-primary)` (normal), `var(--accent-danger)` (if error at that point)
  - Labels below dots: Checkpoint name + timestamp (10px, `var(--text-tertiary)`, rotated 45 degrees if crowded)
- **Hover on dot**: Tooltip card showing:
  - Checkpoint name, timestamp
  - Key metrics at that point: evidence count, faithfulness %, source count
  - Delta from previous checkpoint (e.g., "+42 evidence, +2.3% faithfulness")
- **Click on dot**: Opens State Inspector Drawer (slides in from right, 480px width)

**6.3 State Inspector Drawer**

- **Trigger**: Click any checkpoint dot in the timeline
- **Slide-in**: From right, 480px width, backdrop overlay at 50% opacity
- **Content** (scrollable):
  - **Header**: Checkpoint name + timestamp + close (X) button
  - **Faithfulness Over Iterations**: Line chart (200px height). X-axis: iteration number. Y-axis: faithfulness %. Points connected by line, color-coded (green >= 80%, yellow >= 60%, red < 60%).
  - **Evidence List** (scrollable, max 300px height): Compact list of evidence at this checkpoint. Each row: tier badge + source title (truncated) + relevance score
  - **Error Log**: If errors occurred at this checkpoint, red-bordered section listing each error (timestamp + message)
  - **"Rewind to Here" Button**: `var(--accent-warning)` background. Tooltip: "Resume pipeline from this checkpoint". Requires confirmation modal.
  - **Raw State JSON** (collapsible): `<pre>` block with syntax-highlighted JSON (monospace font, scrollable, max 400px height). Copy button in top-right corner.

**6.4 Reasoning Stream Tab**

- **Position**: Second tab in right panel
- **Layout**: Vertical list of reasoning entries, grouped by pipeline node
- **Group header**: Node name badge (colored pill) + node timestamp range. Collapsible (click to toggle). Default: most recent node expanded, others collapsed.
- **Entry specs**:
  - Timestamp: 11px monospace, `var(--text-tertiary)`, left column (80px)
  - Node badge: Colored pill matching pipeline phase, 10px font
  - Reasoning text: 13px monospace, `var(--text-primary)`, word-wrap. LLM reasoning/thinking text displayed here.
  - Collapsible per entry if text > 200 chars. "Show more / Show less" toggle.

**6.5 Activity Log Tab**

- **Position**: Third tab in right panel
- **Layout**: Chronological list of all pipeline events, newest at top
- **Filter bar** (above list): Filter chips by node type (Plan / Search / Interview / Analyze / Verify / Evaluate / Synthesize / Finalize) + event type dropdown (info / warning / error / all)
- **Entry specs** (same as Activity Log from Screen 2 but with more detail):
  - Timestamp: 11px monospace
  - Node badge: Colored pill
  - Event type icon: info (blue circle-i), warning (yellow triangle), error (red circle-x)
  - Description: 13px, `var(--text-primary)`
  - Detail (collapsible): Additional data, JSON payload, etc.
- **Export button**: "Export Trace" button (top-right of tab) -- downloads full JSONL trace file

---

### Screen 7: Memory Dashboard

**URL Path**: `/memory`

**Layout**: Stats bar at top (full width). Below: two-panel layout. Left panel (50% width) for knowledge cluster visualization. Right panel (50%) for search + item list. On tablet: stacked. On mobile: tabs (Clusters / Items).

#### Elements

**7.1 Stats Bar**

- **Position**: Full width, below header. Height 64px. Background `var(--bg-secondary)` with bottom border.
- **Content**: Horizontal row of stat cards (inline, evenly spaced):
  - Total memory items: Large number + "items" label
  - Items by tier: 3 mini badges (GOLD: N, SILVER: N, BRONZE: N)
  - Items by domain: Top 3 domains as pills
  - Storage size: "{N} MB" with storage icon
- **Style**: Each stat has icon (20px, `var(--accent-primary)`) + value (20px bold) + label (12px `var(--text-secondary)`)

**7.2 Knowledge Clusters (Left Panel)**

- **Visualization**: Bubble chart (D3.js pack layout or force simulation)
- **Each bubble**:
  - Represents a topic cluster
  - Size: Proportional to item count in cluster
  - Color: Gradient mapped to average quality score (low = `var(--accent-danger)` red, medium = `var(--accent-warning)` amber, high = `var(--accent-secondary)` green)
  - Label: Topic name, centered inside bubble if it fits (12px, white), tooltip if too small
  - Border: 1px `var(--border-primary)`
- **Interactions**:
  - Hover: Bubble slightly enlarges (scale 1.05), tooltip with cluster name + item count + avg quality
  - Click: Filters the item list (right panel) to show only items in this cluster. Bubble gets a highlight ring (`var(--accent-primary)` 2px border). Other bubbles dim to 40% opacity.
  - Double-click: Zooms into cluster to show sub-topics (if applicable)
- **Controls**: "Reset" button to clear cluster selection

**7.3 Search + Item List (Right Panel)**

- **Search input**: Full width, 40px height, magnifying glass icon, placeholder "Search memory..."
  - Searches full-text across all LTM item quotes, source titles, and research session names
  - Results update as user types (debounced 300ms)

- **Item list**: Scrollable, below search input. Full width.
- **Item card specs**:
  - Background: `var(--bg-secondary)`, border-left 3px colored by tier
  - Padding: 12px
  - Quote text: 14px, `var(--text-primary)`, 2 lines max, line-clamp
  - Source: 12px, `var(--text-secondary)`, 1 line, with link icon
  - Bottom row (horizontal, space-between):
    - Tier badge (small)
    - Date added: "Added Mar 1"
    - Usage badge: "Used in {N} sessions" (pill, `var(--bg-tertiary)`)
  - Hover: `var(--bg-hover)` background
  - Delete: Swipe-to-delete on mobile (with red "Delete" confirmation). Desktop: X button appears on hover, top-right. Requires confirmation.
  - Click/tap: Expands card to show full quote, all metadata, list of research sessions that used this item

**7.4 Timeline Toggle**

- **Position**: Toggle button above the left panel -- "Clusters" / "Timeline" segmented control
- **Timeline view**: Replaces bubble chart with a line chart
  - X-axis: Date (research sessions chronologically)
  - Y-axis: Cumulative item count
  - Line: `var(--accent-primary)`, 2px
  - Points: Dots at each session, sized by items added in that session
  - Hover on point: Tooltip with session name, date, items added count
  - Click on point: Filters item list to items from that session

---

### Screen 8: Pipeline Editor

**URL Path**: `/editor`

**Layout**: Three-panel layout on desktop. Left sidebar (280px) for template picker + wizard chat. Center canvas (flex-grow) for pipeline DAG visualization. Right panel (320px) for stage configuration. On tablet: canvas only (left sidebar as overlay, right panel as modal). On mobile: wizard chat full-screen, canvas with limited interaction, config as bottom sheet.

#### Elements

**8.1 Template Picker (Left Sidebar, Top Half)**

- **Position**: Top portion of left sidebar, scrollable
- **Section heading**: "Pipeline Templates" (16px, semibold)
- **Template card specs** (vertical list):
  - Background: `var(--bg-secondary)`, border 1px `var(--border-primary)`, border-radius `var(--radius-md)`
  - Padding: 12px
  - Template name: 14px, semibold, `var(--text-primary)`
  - Description: 12px, `var(--text-secondary)`, 2 lines max
  - Bottom row: Stage count badge ("8 stages" pill) + estimated duration ("~45 min" pill) + "Use" button (small, `var(--accent-primary)` outline)
  - Hover: `var(--bg-hover)` background
  - Click "Use": Loads template into pipeline canvas, replaces current pipeline (with confirmation if unsaved changes)
- **Example templates**:
  - "Standard Research" -- 8 stages, ~30 min
  - "Deep Dive" -- 12 stages, ~90 min, includes iterative verification
  - "Quick Summary" -- 5 stages, ~5 min, no STORM interviews
  - "Academic Review" -- 10 stages, ~60 min, prioritizes peer-reviewed sources
  - "Compliance Audit" -- 9 stages, ~45 min, enhanced audit trail

**8.2 Wizard Chat (Left Sidebar, Bottom Half -- AMENDMENT A3)**

- **Position**: Bottom portion of left sidebar, separated by horizontal divider
- **Layout**: Chat interface
- **Message bubbles**:
  - System messages: `var(--bg-tertiary)` background, left-aligned, 13px
  - User messages: `var(--accent-primary)` background, right-aligned, white text, 13px
  - Border-radius: `var(--radius-lg)` (chat bubble shape)
- **Quick-reply chips**: Below the latest system message. Pill buttons (`var(--bg-tertiary)` background, 12px text). Click sends the chip text as a user message.
- **Input**: Text input at bottom of chat area, 36px height, "Type or select..." placeholder, send button (arrow icon)
- **Progress indicator**: Below chat heading, thin progress bar showing "Step 2/6" with step labels. `var(--accent-primary)` fill.
- **CTA Button**: When wizard completes pipeline draft, large "Use This Pipeline" button appears (full width, `var(--accent-primary)` filled, white text, 44px height). Click loads the drafted pipeline into the canvas.
- **Wizard flow** (6 steps):
  1. "What's your research goal?" (free text)
  2. "What type of sources do you want?" (chips: Academic / Web / Internal / All)
  3. "How deep should the analysis go?" (chips: Surface / Standard / Deep / Exhaustive)
  4. "Do you need multi-perspective interviews?" (chips: Yes / No)
  5. "What verification level?" (chips: Basic / Standard / Strict)
  6. "Review your pipeline" (shows summary, "Use This Pipeline" CTA)

**8.3 Pipeline Canvas (Center -- AMENDMENT A4)**

- **Background**: `var(--bg-primary)` with subtle dot grid pattern (dots at every 20px, `var(--border-primary)` color, 1px)
- **Rendering**: SVG-based DAG visualization. Nodes connected by directional edges.

- **Macro-Stage View (Collapsed, Default)**:
  - ~5 large rounded rectangles connected by arrows (left to right)
  - Each macro-stage:
    - Width: 160px, Height: 80px
    - Background: Gradient from `var(--bg-secondary)` to slightly lighter
    - Border: 2px, colored by macro-stage type (search=blue, analyze=orange, verify=green, synthesize=purple, etc.)
    - Border-radius: `var(--radius-lg)`
    - Content: Macro name (14px, semibold, centered), stage count badge ("3 stages" pill below name), estimated duration ("~10 min" below badge)
    - Hover: `var(--shadow-md)` elevation, border brightens
    - Click: Expands this macro to show internal stages; other macros collapse
  - Connecting arrows: Curved bezier lines, 2px, `var(--border-primary)`, with arrowhead at destination

- **Expanded Macro View**:
  - Clicked macro expands to show internal stage DAG
  - Internal stages: Smaller rectangles (120px x 56px), connected by thinner arrows
  - Each stage: Name, type icon, status indicator dot (green=configured, yellow=partial, red=unconfigured)
  - Other macros shrink to icon-only (40px squares) along the top edge
  - Transition: 400ms ease-out expand animation

- **Minimap**: Bottom-right corner, 120px x 80px
  - Shows full pipeline in miniature
  - Viewport rectangle shows current visible area
  - Drag viewport rectangle to pan
  - Click anywhere on minimap to center there

- **Drag-and-drop**: Stages can be dragged between macros. Drop zone highlights (dashed border) when dragging over valid targets.
- **Right-click context menu**: On any stage -- "Delete", "Duplicate", "Configure", "Run Only This Stage"

**8.4 Stage Configuration Panel (Right)**

- **Position**: Right panel, 320px width. Appears when a stage is selected.
- **Content** (scrollable):
  - **Stage header**: Stage name (editable inline) + type dropdown (Search / Analyze / Verify / Synthesize / Custom / etc.)
  - **Parameters section**: Dynamic form based on stage type
    - Each parameter: Label + input (text/number/select/toggle) + help icon (tooltip with description)
    - Example parameters for a "Verify" stage: NLI model selector, confidence threshold (0.0-1.0 slider), max batch size (number input), retry count (number input)
  - **Test button**: "Test Stage" -- runs only this stage with sample data. Shows inline result panel with pass/fail status.
  - **Documentation link**: "View Docs" text link to relevant documentation section
  - **Delete stage button**: Bottom of panel, `var(--accent-danger)` text, requires confirmation

**8.5 Toolbar (Top of Canvas)**

- **Position**: Horizontal bar above the canvas, full width of center panel
- **Buttons** (left-aligned, icon + label):
  - Save (floppy disk icon)
  - Load (folder icon)
  - Validate (checkmark icon) -- runs validation, shows errors inline on offending stages as red badges
  - Run (play icon, `var(--accent-primary)`) -- starts the pipeline with current configuration
- **Validation errors**: When "Validate" is clicked, stages with errors get a red badge (error count) and red border. Clicking the badge shows error details in a tooltip.

---

### Screen 9: Source Conflict View

**URL Path**: Appears as an overlay/panel within the Report View (Screen 3). Not a standalone page.

**Trigger**: Orange "Conflict" badge on report section headings where sources disagree.

#### Elements

**9.1 Conflict Badge**

- **Position**: Inline with section heading, right-aligned
- **Style**: Pill badge, `var(--accent-warning)` background, dark text, 12px font, uppercase "CONFLICT"
- **Icon**: Warning triangle (left of text)
- **Tooltip** (on hover): "{N} sources disagree on this topic"
- **Click**: Opens Conflict Panel

**9.2 Conflict Panel**

- **Trigger**: Click on Conflict badge
- **Desktop**: Overlay panel that expands below the section heading, full width of report body column. Push content below it down (animated, 300ms ease).
- **Mobile**: Bottom sheet, full width, max-height 80vh, scrollable
- **Background**: `var(--bg-tertiary)` with 1px border `var(--accent-warning)` at 50% opacity
- **Border-radius**: `var(--radius-lg)`
- **Padding**: 24px

**9.3 Two-Column Comparison**

- **Layout**: Two columns side by side (desktop), stacked vertically (mobile)
- **Column width**: Equal, 50% each (minus center divider)

- **Left column** ("Source A"):
  - Source title (14px, semibold, linked)
  - Tier badge (GOLD/SILVER/BRONZE)
  - Quote block: `var(--bg-secondary)` background, left border 3px `var(--accent-primary)`, 14px serif text, full quote from source
  - Metadata: Publication year, author, URL
  - Verification verdict badge

- **Right column** ("Source B"):
  - Same structure as Source A
  - Differentiated by different border color: 3px `var(--chart-4)` (purple) left border on quote block

- **Center divider** (desktop only):
  - Vertical line, 1px, `var(--border-primary)`
  - "VS" badge centered on divider: 28px circle, `var(--accent-warning)` background, white text, bold

**9.4 Conflict Analysis Section**

- **Position**: Below the two-column comparison, full width
- **Background**: `var(--bg-secondary)`, border-radius `var(--radius-md)`, padding 16px
- **Content**:
  - **NLI Contradiction Score**: Horizontal bar, 0-1.0 scale, `var(--accent-danger)` fill. Label: "Contradiction confidence: {score}"
  - **Conflicting Claims**: Bulleted list of specific claims where sources disagree. Each bullet: claim text (14px), with source labels ("Source A says... Source B says...")
  - **LLM Reasoning**: Paragraph (13px, `var(--text-secondary)`) explaining the nature of the disagreement, potential reasons, and context
  - **Resolution Explanation**: "How POLARIS resolved this" section:
    - Which source was preferred (highlighted with tier badge)
    - Why: tier comparison, recency comparison, corroboration count comparison
    - Displayed as a simple decision card: "Preferred: {Source A Title} because: {reasons}" with green left border

**9.5 Close Behavior**

- Desktop: Click outside panel or "X" button top-right. Panel collapses with animation (300ms ease).
- Mobile: Swipe down or "X" button. Bottom sheet slides down.

---

## Interaction Patterns

### Transitions

| Trigger | Animation | Duration | Easing |
|---------|-----------|----------|--------|
| Tab switch | CSS opacity fade | 200ms | ease |
| Modal open (desktop) | Fade in + scale from 0.95 to 1.0 | 300ms | ease-out |
| Modal open (mobile) | Slide up from bottom | 300ms | ease-out |
| Modal close | Reverse of open | 200ms | ease-in |
| Panel expand/collapse | Height + opacity | 250ms | ease |
| Theme toggle | CSS custom property transition on `*` for `background-color` and `color` | 200ms | ease |
| Pipeline stepper node completion | Brief pulse (scale 1.0 -> 1.2 -> 1.0) + icon morph (dot -> checkmark) | 400ms | ease-in-out |
| Card hover elevation | Box-shadow transition | 150ms | ease |
| Evidence card stagger | Opacity 0 -> 1 per card | 200ms per card, 50ms stagger delay | ease-out |
| Page navigation | Opacity crossfade | 150ms | ease |
| Drawer slide-in | Transform translateX from 100% to 0 | 300ms | cubic-bezier(0.16, 1, 0.3, 1) |

### Loading States

| Context | Loading Indicator | Description |
|---------|-------------------|-------------|
| Initial page load | Skeleton placeholders | Gray rounded rectangles matching content layout dimensions. Subtle shimmer animation (gradient sweep left-to-right, 1.5s infinite). |
| Pipeline running | Pulsing status text + animated counters + progress bar | Status text has animated ellipsis. Counters animate on increment. Progress bar fills smoothly. |
| Data fetching (any component) | Inline spinner | 20px circular spinner (`var(--accent-primary)`) placed inside the requesting component. NOT a full-page overlay. |
| Evidence cards loading | Staggered fade-in | Cards appear one by one with 50ms delay between each, 200ms fade-in duration |
| PDF export generating | Button spinner | Export button text changes to "Generating..." with inline spinner replacing the icon. Button disabled during generation. |
| Mind map loading | Animated node placement | Nodes appear from center outward in concentric rings, 100ms delay per ring |

### Empty States

Every view has a designed empty state. Never show a blank white/dark screen.

| View | Empty State Design |
|------|-------------------|
| No research history | Centered illustration (abstract line art of a research pipeline). Heading: "Start your first research query" (20px, semibold). Subtext: "Type a question above to begin deep research" (14px, `var(--text-secondary)`). Arrow illustration curving up toward the search input. |
| No evidence (pre-research) | Illustration of a magnifying glass over documents. "Run a research query to see evidence" with arrow pointing up toward the search input. |
| Operator view (no run) | Pipeline stepper in all-pending state (all gray dots). "Pipeline metrics will appear here when you run a query." Below: "Start a query from the Research tab" link. |
| Memory dashboard empty | Illustration of a brain with connection nodes. "Research findings will accumulate here across sessions." Subtext: "Each completed research query adds verified findings to long-term memory." |
| Evidence browser with filters showing 0 results | "No evidence matches your filters." "Try adjusting the tier or search criteria." Reset filters button. |
| Pipeline editor (no pipeline loaded) | "Choose a template or use the wizard to build your pipeline." Arrow pointing to left sidebar template list. |

### Error States

| Error Type | Display | Actions |
|-----------|---------|---------|
| Pipeline error | Red status badge replaces green/blue in stepper. Error message in plain language (not stack trace) displayed in status center area. | "Retry" button (primary) + "View Details" collapsible panel with technical error info (monospace, scrollable) |
| Network error / SSE disconnect | Toast notification (top-right, 320px wide). `var(--accent-warning)` left border. Icon: wifi-off. Text: "Connection lost -- retrying..." Progress bar below text showing retry attempt countdown. | Auto-retry with exponential backoff (2^n seconds, max 30s, 10 retries). "Retry Now" text button. |
| Export error | Toast notification. `var(--accent-danger)` left border. Specific failure reason (e.g., "PDF generation failed: report too large"). | "Try Again" button in toast. |
| Citation preview unavailable | In citation popover Tab 1: replace iframe with blockquote showing cited text on `var(--bg-tertiary)` background. | "View Original" link button to open source URL in new tab. |
| Auth error (401) | Full-screen overlay with lock icon. "Session expired. Please log in again." | Login button redirecting to auth flow. |
| Rate limit (429) | Toast notification. "Too many requests. Please wait {N} seconds." Countdown timer in toast. | Auto-dismiss when cooldown expires. |

### Toast Notification System

- **Position**: Top-right corner, 16px from edges
- **Stack**: Multiple toasts stack vertically (newest on top), 8px gap
- **Width**: 320px (desktop), calc(100% - 32px) on mobile
- **Duration**: Auto-dismiss after 5s (info), 8s (warning), persistent until dismissed (error)
- **Structure**: Left colored border (4px) + icon (20px) + title (14px bold) + message (13px) + close X button
- **Colors**: Info = `var(--accent-primary)`, Success = `var(--accent-secondary)`, Warning = `var(--accent-warning)`, Error = `var(--accent-danger)`
- **Animation**: Slide in from right (200ms), fade out (200ms)

---

## Responsive Behavior

### Mobile (375px)

- **Single column layout everywhere**. No side-by-side panels.
- **Header**: Compact. Logo + hamburger menu. Tabs in horizontal scroll bar below header (44px height).
- **TOC**: Hidden. Accessible via hamburger menu (overlay from left, 280px width, backdrop blur).
- **Evidence cards**: Stack vertically, 1 column, full width.
- **Pipeline stepper**: Horizontal scroll with active node centered. Gradient fade indicators on edges.
- **Mind map**: Full viewport. Pinch-to-zoom, tap-to-select. No hover tooltips (tap shows info card instead).
- **Citation interaction**: Full-screen bottom sheet (swipe down to dismiss, drag handle at top).
- **Pipeline editor wizard chat**: Full-screen overlay.
- **Conflict view**: Stacked vertically (Source A above Source B).
- **Filter bars**: Horizontally scrollable chip rows.
- **Modals**: Always full-screen bottom sheets.
- **Touch targets**: Minimum 44px x 44px for all interactive elements.
- **Font sizes**: Body text minimum 16px to prevent iOS zoom.

### Tablet (768px)

- **Report**: Body centered (max 640px) + collapsible sidebar (slides in from right as overlay).
- **Evidence**: 2-column masonry grid.
- **Pipeline editor**: Canvas only. Template picker as slide-in overlay from left. Config panel as modal overlay.
- **Mind map**: Full viewport with floating control toolbar.
- **Operator console**: Stacked -- metrics panel full width at top, tabbed content below.
- **Memory dashboard**: Stacked -- clusters above, item list below.
- **Conflict view**: Two columns maintained but narrower (each 48% width).

### Desktop (1440px)

- **Report**: 3-column layout. TOC (220px) + body (max 720px) + source sidebar (280px).
- **Evidence**: 3-column masonry + detail panel (400px slide-in from right).
- **Pipeline editor**: Full 3-panel layout. Left sidebar (280px) + canvas (flex-grow) + config panel (320px).
- **Mind map**: Full viewport with sidebar filter panel (280px) and floating control toolbar.
- **Operator console**: 2-panel split. Left metrics (360px) + right tabbed content.
- **Memory dashboard**: 2-panel side by side. Clusters (50%) + search/list (50%).
- **Hover states**: All hover interactions active (tooltips, card elevation, link underlines).
- **Keyboard shortcuts**:
  - `Ctrl+K` / `Cmd+K`: Focus search input
  - `Ctrl+E` / `Cmd+E`: Toggle evidence browser
  - `Ctrl+M` / `Cmd+M`: Toggle mind map
  - `Escape`: Close any modal/panel/drawer
  - `1-9`: Switch between tabs in active view
  - `R`: Toggle Researcher/Operator mode

---

## Component Library Summary

The following reusable components should be designed as part of the design system:

| Component | Variants | Usage |
|-----------|----------|-------|
| `Button` | Primary, Secondary, Outline, Danger, Ghost, Icon-only | All CTAs and actions |
| `Badge` | Tier (Gold/Silver/Bronze), Status (Running/Complete/Error), Faithfulness, Count, Conflict | Labels and indicators |
| `Card` | Evidence, Source, History, Template, Finding, Memory Item | Content containers |
| `Input` | Search (with icon), Text, Number, Select, Textarea | Form controls |
| `Chip` | Filter (toggleable), Depth selector (radio-like), Quick-reply | Selection and filtering |
| `Modal` | Standard, Confirmation, Full-screen (mobile) | Dialogs |
| `Toast` | Info, Success, Warning, Error | Notifications |
| `Popover` | Citation, Tooltip, Context menu | Contextual information |
| `Drawer` | Right slide-in, Bottom sheet (mobile) | Detail panels |
| `Chart` | Radar (5-axis), Ring/Donut, Line, Bar (horizontal), Bubble | Data visualization |
| `Stepper` | Pipeline (horizontal, 8 nodes) | Progress indication |
| `Skeleton` | Text line, Card, Chart, Table row | Loading placeholders |
| `Timeline` | Checkpoint (horizontal with dots) | Temporal data |
| `Tab` | Standard, Segmented control, Scrollable | Navigation |
| `EmptyState` | With illustration + CTA | Blank view states |

---

## Design Deliverables Checklist

When producing wireframes or mockups from this brief, ensure the following are delivered:

1. [ ] **Screen 1**: Landing / Research Input -- desktop + mobile
2. [ ] **Screen 2**: Active Research (pipeline running) -- desktop + mobile
3. [ ] **Screen 3**: Report View with TOC, citations, smart art -- desktop + tablet + mobile
4. [ ] **Screen 3a**: Citation popover (3 tabs) -- desktop + mobile
5. [ ] **Screen 4**: Evidence Browser (grid + list + graph views) -- desktop + mobile
6. [ ] **Screen 5**: Mind Map View with all node types -- desktop + mobile
7. [ ] **Screen 6**: Operator / Pipeline Console -- desktop
8. [ ] **Screen 6a**: State Inspector Drawer -- desktop
9. [ ] **Screen 7**: Memory Dashboard (clusters + timeline) -- desktop + mobile
10. [ ] **Screen 8**: Pipeline Editor with wizard chat -- desktop + tablet
11. [ ] **Screen 9**: Source Conflict View (inline in report) -- desktop + mobile
12. [ ] **Component library**: All components listed above with states (default, hover, active, disabled, error)
13. [ ] **Dark theme** and **light theme** versions of at least Screen 1, Screen 3, and Screen 5
14. [ ] **Empty states** for all views
15. [ ] **Error states** for pipeline failure, network loss, and export failure
16. [ ] **Loading states** with skeleton screens for Screen 1, Screen 3, and Screen 4
17. [ ] **Responsive layouts** at 375px, 768px, and 1440px for Screen 3 and Screen 4

---

## Technical Implementation Notes

These notes are for the engineering team implementing the designs, not for the design phase itself.

- The dashboard is currently a monolithic HTML file (~7,800 lines). The redesign will modularize it into ~18 ES module files.
- All data comes from a FastAPI backend via REST endpoints and SSE (Server-Sent Events) for real-time updates.
- The pipeline runs in Python (LangGraph). The frontend communicates via `/api/research`, `/api/events` (SSE), and `/api/research/result/{vector_id}`.
- View mode toggle (Researcher/Operator) is implemented via CSS class toggle (`body.user-mode`) and `localStorage` persistence.
- Mermaid diagrams are rendered client-side via Mermaid.js.
- Mind map and evidence graph use D3.js for force-directed and radial layouts.
- Charts (radar, line, bar, ring) use either D3.js or lightweight SVG generation.
- The application is a SPA (Single Page Application) with client-side routing.
- All color tokens are CSS custom properties for theme switching.
- The `POLARIS_DEPLOYMENT_MODE` env var (cloud/sovereign) affects the deployment badge in the header.

---

*This document is the authoritative UI/UX specification for the POLARIS Research Intelligence Platform. When given to a design-capable AI model with the instruction to produce Figma-ready wireframes, it should produce complete, consistent, and production-quality UI specifications for all 9 screens plus the design system.*

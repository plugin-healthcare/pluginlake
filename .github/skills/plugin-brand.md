# PLUGIN Style Guide

> **PLUGIN** — platform voor uitwisseling en hergebruik van klinische data Nederland

This document defines the visual identity and styling rules for PLUGIN. Use it as a reference when generating pages, documentation, presentations, or any branded material.

---

## Brand Identity

PLUGIN is a Dutch national platform for clinical data exchange and reuse across hospital networks. The visual identity conveys **reliability** (blue tones), **healthcare** (medical iconography), and **data connectivity** (the circle cluster motif is based on cross-sections of a data cable, with varying sizes representing data diversity).

---

## Color Palette

| Role | Name | Hex | RGB | Usage |
|---|---|---|---|---|
| Primary dark | Navy | `#053c5c` | `rgb(5, 60, 92)` | Headings, primary text, dark backgrounds |
| Primary | Teal | `#0588a6` | `rgb(5, 136, 166)` | Links, buttons, accents, interactive elements |
| Primary light | Light blue | `#bbe2ee` | `rgb(187, 226, 238)` | Backgrounds, cards, highlights, secondary fills |
| Accent | Orange | `#f28729` | `rgb(242, 135, 41)` | Call-to-action, emphasis, alerts, sparingly used accents |

### Extended palette (derived)

| Role | Hex | Usage |
|---|---|---|
| Background | `#f7fbfd` | Page background (very light blue-white) |
| Surface | `#ffffff` | Card and content area backgrounds |
| Text primary | `#053c5c` | Body text |
| Text secondary | `#3a6a82` | Muted/secondary text |
| Border | `#d4e8f0` | Dividers, card borders, table lines |
| Success | `#0588a6` | Confirmations (use teal, not green) |
| Warning | `#f28729` | Warnings |
| Error | `#c0392b` | Errors |

### Color ratios and usage

- Use **navy** and **teal** as the dominant colors (~80% of colored surface area).
- Use **light blue** for large background areas and subtle fills (~15%).
- Use **orange sparingly** for emphasis and calls to action (~5%).
- Never use orange for large fills or backgrounds.

---

## Typography

| Element | Font | Weight | Size guidance |
|---|---|---|---|
| Brand wordmark | Adobe Clean | Regular | As per logo artwork |
| Headings (H1) | System sans-serif fallback stack | Bold (700) | 2rem / 32px |
| Headings (H2) | System sans-serif fallback stack | Semibold (600) | 1.5rem / 24px |
| Headings (H3) | System sans-serif fallback stack | Semibold (600) | 1.25rem / 20px |
| Body | System sans-serif fallback stack | Regular (400) | 1rem / 16px |
| Small / caption | System sans-serif fallback stack | Regular (400) | 0.875rem / 14px |
| Code | Monospace stack | Regular (400) | 0.9rem / 14.4px |

### Font stack

```css
--font-body: "Adobe Clean", "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
--font-mono: "JetBrains Mono", "Fira Code", "Source Code Pro", monospace;
```

> If Adobe Clean is unavailable, fall back to Inter or the system sans-serif stack. The brand identity relies more on color and spacing than on a specific typeface.

### Heading color

- H1: `#053c5c` (navy)
- H2, H3: `#053c5c` (navy)
- Body text: `#053c5c` (navy) at 90% opacity, or `#1a4a66`

---

## Logo

### Variants

| Variant | File | Use case |
|---|---|---|
| Full logo with icons | `assets/logo_plugin_rgb_groot_met_iconen_kleur.png` | Hero sections, landing pages, large displays (2000x713px) |
| Favicon / icon only | `assets/logo_plugin_rgb_flavicon.png` | Browser favicon, app icon, small UI placements (1024x1024px) |

### Logo placement rules

- Always provide sufficient clear space around the logo (minimum: height of the "P" in PLUGIN on all sides).
- The full logo works on both light and dark backgrounds due to built-in transparency effects.
- For small sizes: use the icon-only variant (without medical icons, without subtitle text).
- For favicon: use the circle cluster mark only.
- Never stretch, rotate, recolor, or place the logo on visually busy backgrounds without a container.

### Referencing logos in docs (e.g., MkDocs, Sphinx)

```yaml
# mkdocs.yml example
theme:
  logo: assets/logo_plugin_rgb_groot_met_iconen_kleur.png
  favicon: assets/logo_plugin_rgb_flavicon.png
```

```rst
# Sphinx conf.py example
html_logo = "_static/logo_plugin_rgb_groot_met_iconen_kleur.png"
html_favicon = "_static/logo_plugin_rgb_flavicon.png"
```

---

## Component Styling

### Buttons

| Type | Background | Text | Border |
|---|---|---|---|
| Primary | `#0588a6` | `#ffffff` | none |
| Primary hover | `#047a96` | `#ffffff` | none |
| Secondary | `transparent` | `#0588a6` | `1px solid #0588a6` |
| Accent / CTA | `#f28729` | `#ffffff` | none |

### Cards

- Background: `#ffffff`
- Border: `1px solid #d4e8f0`
- Border-radius: `8px`
- Shadow: `0 1px 3px rgba(5, 60, 92, 0.08)`

### Code blocks

- Background: `#f0f6fa`
- Border: `1px solid #d4e8f0`
- Border-radius: `6px`
- Text: `#053c5c`
- Padding: `1rem`

### Tables

- Header background: `#053c5c`
- Header text: `#ffffff`
- Row alternate: `#f7fbfd`
- Border: `1px solid #d4e8f0`

### Alerts / admonitions

| Type | Left border color | Background |
|---|---|---|
| Info / Note | `#0588a6` | `#eef7fa` |
| Warning | `#f28729` | `#fef5ec` |
| Error / Danger | `#c0392b` | `#fdecea` |
| Tip / Success | `#0588a6` | `#eef7fa` |

---

## Spacing & Layout

- Base spacing unit: `8px`
- Content max-width: `1200px`
- Paragraph spacing: `1.5 * base` = `12px`
- Section spacing: `4 * base` = `32px`
- Line height body: `1.6`
- Line height headings: `1.3`

---

## CSS Custom Properties (copy-paste ready)

```css
:root {
  /* Brand colors */
  --color-navy: #053c5c;
  --color-teal: #0588a6;
  --color-light-blue: #bbe2ee;
  --color-orange: #f28729;

  /* Semantic colors */
  --color-bg: #f7fbfd;
  --color-surface: #ffffff;
  --color-text: #053c5c;
  --color-text-muted: #3a6a82;
  --color-border: #d4e8f0;
  --color-link: #0588a6;
  --color-link-hover: #047a96;
  --color-accent: #f28729;
  --color-error: #c0392b;

  /* Typography */
  --font-body: "Adobe Clean", "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  --font-mono: "JetBrains Mono", "Fira Code", "Source Code Pro", monospace;
  --font-size-base: 1rem;
  --line-height-body: 1.6;
  --line-height-heading: 1.3;

  /* Spacing */
  --space-unit: 8px;
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 32px;
  --space-xl: 64px;

  /* Radii */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 16px;
}
```

---

## MkDocs Material Theme Override (example)

If using MkDocs with the Material theme, add this to `docs/stylesheets/plugin_theme.css`:

```css
:root,
[data-md-color-scheme="default"] {
  --md-primary-fg-color: #053c5c;
  --md-primary-fg-color--light: #0588a6;
  --md-primary-fg-color--dark: #032a42;
  --md-accent-fg-color: #f28729;
  --md-default-fg-color: #053c5c;
  --md-typeset-a-color: #0588a6;
}

[data-md-color-scheme="slate"] {
  --md-primary-fg-color: #0588a6;
  --md-accent-fg-color: #f28729;
}
```

```yaml
# mkdocs.yml
extra_css:
  - stylesheets/plugin_theme.css
```

---

## Do's and Don'ts

**Do:**
- Use navy for text and headings to maintain readability.
- Use teal for interactive elements (links, buttons).
- Use orange only for small, high-impact accents.
- Maintain generous whitespace.
- Use the appropriate logo variant for the context size.

**Don't:**
- Use orange as a background color or for large areas.
- Mix the brand colors with unrelated hues.
- Place the full logo at very small sizes (use the favicon variant instead).
- Use low-contrast color combinations (e.g., light blue text on white).
- Modify logo colors or proportions.

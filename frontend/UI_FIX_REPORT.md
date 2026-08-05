# UI Fix Report

Date: 2026-08-05

## Fixed customer web issues

- Added the missing padding to content cards on event detail, seat selection, checkout, booking, account and ticket screens.
- Added spacing between ticket-type cards and the booking form.
- Added stable grid spacing for checkout and seat selection so labels, inputs, help text and buttons no longer touch card borders.
- Added the missing styles for `detail-main`, information notices and the QR placeholder.
- Improved sticky booking summaries, text wrapping, mobile fact rows and long identifiers.
- Removed stale visual-evidence screenshots that showed the old broken layout.

## Fixed admin web issues

- Restored the missing compatibility aliases between the admin stylesheet and shared UI design tokens. Undefined variables were the main reason the page fell back to default serif fonts and unstyled controls.
- Added the missing base `.card` style used throughout the operations dashboard.
- Rebuilt the admin sign-in layout with a styled form, responsive operations panel, focus states and accessible error presentation.
- Added client-side validation for the Identity password minimum before sending the request, replacing the generic `Request validation failed` case shown in the screenshot.
- Fixed health-row and table-cell layouts and improved dashboard top-bar spacing.

## Verification

- `npm run typecheck`: PASS for customer-web and admin-web.
- CSS parse with PostCSS: PASS for customer, admin and shared UI stylesheets.
- CSS variable audit: no unresolved variables after combining each app stylesheet with shared tokens.
- Class audit: all static application classes used by the pages have matching local or shared styles.

## Build note

The uploaded archive contains Windows-specific `node_modules` binaries for Rollup and esbuild. A Linux build cannot use those binaries. This is not a TypeScript or UI source failure. Install dependencies on the target machine before building:

```bash
npm install
npm run typecheck
npm run build
```

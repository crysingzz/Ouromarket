# Restyle the operator interface

## Why

The current dashboard is visually dense and uses a conventional administration layout. The requested direction is closer to cobalt.tools: a compact navigation rail, black canvas, monochrome controls, generous negative space, rounded controls and clear active state. The application must gain that character without copying cobalt artwork, branding or source and without hiding the platform's safety state.

## What Changes

- Replace the wide sidebar with an original compact icon-and-label rail whose active item becomes a light tile.
- Move the interface to a black and graphite palette with monospaced typography, subtle borders and restrained status colors.
- Recompose headings, metrics, panels, tables, forms, dialogs and notifications around a lighter visual hierarchy and larger working canvas.
- Turn the rail into a fixed bottom dock on narrow screens while preserving accessible names and all existing navigation targets.
- Add automated computed-style, overflow, desktop/mobile and full workflow browser acceptance.

## Impact

This is a presentation change. Existing element identifiers, API calls, authentication, operator actions, research state and capital restrictions remain unchanged. No cobalt asset, mascot, logo, font or application source is included.

# Design

The new interface uses the reference's structural ideas rather than its identity. A 92-pixel graphite rail carries an original `>>` mark and seven compact operator destinations. The selected destination is a warm-white tile with black text. A pure black canvas, system monospace stack, hairline graphite boundaries and small colored status indicators create a quiet control surface. The alpha emblem and all icons are local text/CSS primitives.

Content remains information-dense where the product requires it, but visual weight moves from filled cards to spacing, alignment and borders. Metrics use a four-cell strip, major workflows use low-contrast panels, and destructive controls keep an explicit red treatment. Forms and dialogs use the same black input wells and light primary action as the reference direction.

At 760 pixels and below, the rail becomes a bottom dock. Labels shorten visually while each button keeps its full accessible name. The main canvas reserves dock space, two-column layouts collapse, data tables retain horizontal scrolling inside their own boundary, and dialogs remain within the viewport. Reduced-motion preferences disable decorative transitions.

Browser acceptance reads computed styles instead of trusting class names. It checks desktop rail geometry, active contrast, black canvas, mobile bottom docking, content clearance, overflow and JavaScript errors. The existing end-to-end UI smoke continues to exercise every operator workflow.

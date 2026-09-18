## ADDED Requirements

### Requirement: Compact operator navigation

The interface SHALL present every existing application section through a compact navigation rail with a visually distinct active item and an accessible full section name. On narrow viewports the same destinations SHALL become a bottom dock without covering the active page content.

#### Scenario: Operator changes viewport width

- **WHEN** the authenticated interface changes between desktop and mobile widths
- **THEN** every destination remains reachable, the active destination remains identifiable and the document has no horizontal overflow

### Requirement: Restrained control-surface hierarchy

The interface SHALL use an original monochrome control-surface theme with a black canvas, graphite boundaries, light primary actions and restrained semantic status colors. Safety state, synthetic mode and destructive actions SHALL remain visibly distinct.

#### Scenario: Overview is rendered

- **WHEN** the operator opens the overview
- **THEN** metrics, research flow, independent control state and recent evidence remain readable without requiring color alone to communicate their meaning

### Requirement: Workflow and accessibility preservation

The restyle SHALL retain existing element identities, workflows, keyboard focus indicators and responsive dialog bounds. It SHALL NOT add external artwork, fonts, analytics or runtime resources.

#### Scenario: Full browser workflow runs after restyle

- **WHEN** login, research, evidence, risk, audit, autonomous research and lifecycle actions are exercised on desktop and mobile
- **THEN** the workflow completes without a JavaScript error, inaccessible navigation target or page-level horizontal overflow

## ADDED Requirements

### Requirement: Frozen post-activation performance monitoring

Each new internal-paper activation SHALL retain an immutable monitoring admission bound to the transition, source, dataset, origin, cost protocol and qualifying comparison. The admission SHALL freeze paper-performance-v1: ten daily return intervals per window, a maximum 21 calendar days per window, a net loss of at least 0.5%, a shortfall of at least one percentage point from the qualification reference, and two consecutive breaches before demotion. The reference SHALL be the geometric ten-interval equivalent of the qualifying net return and SHALL NOT be presented as a forecast or statistical alpha estimate.

#### Scenario: Sustained net deterioration

- **WHEN** two consecutive comparable windows each meet both loss and shortfall thresholds
- **THEN** the server retains both reports and atomically demotes the strategy, clears its active pointer and halts its internal paper account
- **AND** the demotion references the retained performance report and grants no replacement strategy trading authority

#### Scenario: No cherry-picking or retrospective change

- **WHEN** the worker receives a duplicate daily sample, late historical sample or a later server policy version
- **THEN** previously sealed daily observations, completed reports and the admitted policy remain unchanged
- **AND** adjacent windows share only their endpoint observation, with no overlapping return intervals

#### Scenario: Incomparable observations or recovery

- **WHEN** a completed window mixes origins, differs from the admitted identity or spans more than 21 calendar days
- **THEN** the report is INCONCLUSIVE and breaks the consecutive-breach count
- **WHEN** a comparable window does not meet both loss and shortfall thresholds
- **THEN** it also resets the consecutive-breach count

#### Scenario: Independent authority and evidence

- **WHEN** an agent attempts to submit monitoring scores or change the admitted policy through the API
- **THEN** no such write interface is available
- **AND** authorized operators can inspect the immutable admission, source observations, result hashes and decisions
- **AND** independent risk stops retain priority over performance monitoring

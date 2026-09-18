# Portfolio and Independent Risk

## Purpose

Platform contract for portfolio and independent risk. Initial implementation and target-only requirements are distinguished in docs/STATUS.md.

## Requirements

### Requirement: Mandatory deterministic risk
Every new paper order SHALL be checked against server-owned prices, holdings, cash, concentration, strategy allocation, gross exposure, volatility, CVaR, drawdown and daily loss.

#### Scenario: Limit breach
- **WHEN** an order would violate any mandatory limit
- **THEN** the order is rejected and no fill is recorded

### Requirement: Fail closed
Trading MUST be blocked on stale or invalid quotes, missing risk data, reconciliation mismatch, unavailable persistence or active kill switch.

#### Scenario: Stale quote
- **WHEN** a quote is older than policy permits
- **THEN** the order is halted and no position is created

### Requirement: Operator-only emergency stop
Only an operator SHALL control the persistent kill switch.

#### Scenario: Agent requests resume
- **WHEN** research identity calls resume
- **THEN** the API returns forbidden and the halt remains active

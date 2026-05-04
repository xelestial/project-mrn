# Browser E2E Fixture Scenarios

Status: `AUTOMATED BASELINE`

This directory tracks browser-facing scenario fixtures for parity gates.

Current scenarios:

1. `fixtures/non_default_topology_line_3seat.json`
2. `fixtures/manifest_hash_reconnect.json`
3. `fixtures/parameter_matrix_economy_dice_2seat.json`

Automated usage:

1. Install dependencies in `apps/web`.
2. Install Playwright browser:
   - `npx playwright install --with-deps chromium`
3. Run browser e2e:
   - `npm run e2e`
4. CI pipeline (`.github/workflows/ci.yml`) runs this as parity gate.

Current automated checks:

1. `parity.spec.ts :: non-default topology fixture renders line board and 3-seat lobby options`
2. `parity.spec.ts :: manifest-hash reconnect fixture rehydrates projection after session switch`
3. `parity.spec.ts :: parameter matrix fixture rehydrates seat/economy/dice assumptions`

Notes:

- Fixture JSON files remain versioned artifacts and human-readable scenario references.
- Playwright tests consume fixture identity and enforce DOM-level parity behavior.

# [REPORT] UI/UX Validation And Commercial Benchmark 2026-04-15

Status: CLOSED_MERGED_REFERENCE  
Updated: 2026-04-15  
Scope: `apps/web` current implementation audit + commercial benchmark-backed UI refinement direction

Merged into:
- `docs/frontend/[ACTIVE]_UI_UX_FUTURE_WORK_CANONICAL.md`

---

## 1. Executive Summary

Current UI/UX documentation is not uniformly stale.
The active execution guides are still broadly valid, but the older proposal documents now mix:

- ideas that have already shipped
- ideas that remain useful as references
- pixel/layout assumptions that no longer match the live implementation

The current web UI has improved in readability, but it still carries one large commercial-quality gap:

**the screen is functionally zoned, but not visually zoned.**

Right now most surfaces share the same navy family:

- page background: dark blue radial gradient
- player strip cards: dark blue cards with light text
- prompt shell: dark blue shell with gold border
- summary pills and context chips: dark blue again

This keeps the UI consistent, but it also flattens priority.
Commercial games with similar board/card/party hybrids do the opposite:

- the board stays visually dominant
- urgent decisions get a warmer/focused treatment
- player identity uses strong seat colors
- economy/risk/special states get their own semantic hues

The recommendation is **not** to switch to a rainbow UI.
It is to keep the current dark-fantasy/navy base, but split it into a clearer commercial palette system:

1. base world / board navy
2. decision amber-gold
3. economy success/failure green/red
4. stable per-player jewel accents

---

## 2. Validity Check Of Current UI/UX Docs

### A. Still valid as execution sources

#### `docs/frontend/[ACTIVE]_UI_UX_PRIORITY_ONE_PAGE.md`

Status: **still valid, but partially completed**

What remains true:

- board-first layout is the right direction
- top rail should stay compact
- prompt reason/context must be visible
- active player visibility matters more than decorative polish

What is no longer current as written:

- some P0 fixes are already implemented
  - current actor emphasis exists in the match player strip
  - raw bracket tags like `[효과]` are now cleaned in `PromptOverlay.tsx`
- several file-level instructions point to older component boundaries
  - the live match now relies heavily on `App.tsx` match-table composition, not only older panel components

Conclusion:
keep this as the **priority lens**, not as a literal patch checklist.

#### `docs/frontend/[PLAN]_BOARD_COORDINATE_SYSTEM_AND_HUD_LAYOUT_STABILIZATION.md`

Status: **valid and still partially open**

Still valid:

- prompt shell height budgeting
- hand tray 5-slot grid assumption
- board-safe vertical budget rules

Still open:

- moving remaining viewport-owned compensations out of `App.tsx`
- consolidating prompt/tray anchoring into board-owned layout metadata

Conclusion:
this remains the correct layout stabilization plan.

#### `docs/frontend/[PLAN]_LIVE_PLAY_STATE_AND_DECISION_RECOVERY.md`

Status: **valid and still open**

Still valid:

- purchase legality
- resolution order correctness
- stable card identity
- selector/data-source hardening

Conclusion:
this is still the authoritative document for unresolved gameplay-facing UI/runtime correctness.

### B. Valid as reference, not as execution source

#### `docs/frontend/[PROPOSAL]_UI_UX_COMMERCIAL_REDESIGN.md`

Status: **useful reference, not literal implementation guide**

Still useful:

- zone-based thinking
- EventFeed / PromptPanel / player-bar decomposition ideas
- stronger commercial readability goals

Not fully current:

- component names and phase steps no longer match the exact shipped composition
- some assumptions are pre-layout-tuning and pre-latest prompt refactors

Conclusion:
use for **design direction**, not for file-by-file execution.

#### `docs/frontend/[PROPOSAL]_UI_UX_DETAILED_SPEC.md`

Status: **partially stale**

Still useful:

- event feed data shape ideas
- spacing/structure intentions

Stale:

- several pixel-exact assumptions no longer match current CSS tokens and safe-band tuning

Conclusion:
reuse structural ideas, do not treat the pixel spec as canonical.

#### `docs/frontend/[PROPOSAL]_UI_UX_REDESIGN_FROM_SCRATCH.md`

Status: **historical inspiration only**

Conclusion:
do not use as an execution plan unless a full redesign is explicitly restarted.

#### `docs/frontend/[PROPOSAL]_UI_UX_ISSUE_FIX_PLAN.md`

Status: **regression ledger, partly obsolete**

Useful:

- earlier bug framing
- regression memory

Obsolete:

- several listed issues are already resolved or have moved

Conclusion:
keep as reference only.

---

## 3. Current Implementation Audit

Based on current code:

- `apps/web/src/styles.css`
- `apps/web/src/App.tsx`
- `apps/web/src/features/prompt/PromptOverlay.tsx`

### Confirmed strengths

1. The screen is much more board-first than before.
2. The player strip is compact enough for 1920x1080.
3. The prompt shell now has a top timer bar and a tighter vertical budget.
4. Local player / seat type / current prompt ownership are more legible than older proposals assumed.
5. Trick text cleanup is already in place.

### Confirmed design limitations

1. **Monochrome surface stacking**
   - player cards, prompt shell, pills, and many chips all live in the same blue family
   - result: urgency and hierarchy depend too much on text and borders

2. **Gold is overloaded**
   - gold currently signals timer, border emphasis, active selection, and premium highlight
   - result: the user does not get a clean “decision vs status vs reward” distinction

3. **Player identity is still text-first**
   - the seat color exists, but most of the player strip still reads as the same card repeated 4 times
   - commercial titles usually let the user identify seats by color and silhouette first, text second

4. **Prompt context chips are semantically flat**
   - most chips use similar blue badges
   - cost, danger, ownership, target scope, and timer context need stronger visual categories

5. **Container count is still slightly high**
   - the current UI is better, but some trays still feel like containers inside containers
   - commercial UIs often reduce chrome and let typography, iconography, and color carry the hierarchy

---

## 4. Commercial Benchmark Set

The titles below were chosen because they overlap with the project in at least one of these ways:

- multiplayer board readability
- compact player HUD design
- card/prompt decision clarity
- “party chaos + strategy” information density

### 1. Mario Party Superstars

Source:
- [Nintendo official product page](https://www.nintendo.com/us/store/products/mario-party-superstars-switch/)

Why it matters:

- board game readability
- 4-player identity clarity
- fast recognition under chaotic outcomes

Benchmark takeaways:

- the board remains the hero; UI stays secondary until interaction is needed
- each player has a strong seat identity color
- important info is chunked into small, bright, instantly readable widgets
- large text is reserved for primary outcomes, not constant status noise

What to borrow:

- stronger per-seat color identity
- less repeated framing around player stats
- reserve bright/high-saturation moments for actual turn drama

### 2. Dokapon Kingdom: Connect

Source:
- [Steam product page](https://store.steampowered.com/app/2338140/Dokapon_Kingdom_Connect/)

Why it matters:

- fantasy board/RPG party hybrid
- close to this project’s “friendly surface, malicious outcomes” tone

Benchmark takeaways:

- fantasy UI works better with layered material contrast than with one flat hue
- parchment/gold framing plus colored stat accents keeps the screen lively without losing theme
- state changes are easier to parse when economy, danger, and ownership are color-separated

What to borrow:

- a fantasy-material split: dark world background + warmer decision panel
- use accent colors for resource classes instead of only for borders

### 3. 100% Orange Juice

Source:
- [Steam product page](https://store.steampowered.com/app/282800/100_Orange_Juice/)

Why it matters:

- digital multiplayer board game with cards, dice, and sudden reversals

Benchmark takeaways:

- lightweight panels and clear player colors keep the board from being visually buried
- turn/state information is short and immediate
- the tone is playful, but the UI still assigns each information type a distinct visual role

What to borrow:

- lighter chrome around repeated panels
- more seat-color ownership in the player strip and hand/trick area

### 4. Balatro

Source:
- [Steam product page](https://store.steampowered.com/app/2379780/Balatro)

Why it matters:

- top-tier commercial decision readability
- dark background + high-focus card/action presentation

Benchmark takeaways:

- the background can stay dark and subdued if the decision surface gets a warmer focal treatment
- chip badges and counters work best when each color has a job
- the most important action area should feel “lit” relative to the rest of the screen

What to borrow:

- warmer prompt/action focal zone
- stronger emphasis for primary action buttons and selected cards
- less dependence on borders alone

### 5. Cobalt Core

Source:
- [Steam product page](https://store.steampowered.com/app/2179850/Cobalt_Core/)

Why it matters:

- dense tactics/card UI with good panel separation

Benchmark takeaways:

- cool background + warm action + danger accent is a very efficient hierarchy
- compact interfaces feel clearer when semantic colors do the sorting work

What to borrow:

- explicit semantic color channels
- decision emphasis without adding more panel furniture

---

## 5. Recommended Color Strategy

This section is an **inference from official screenshots and store presentation**, not a sampled brand palette.
The goal is not to clone another game.
The goal is to move from “one navy system” to “one world palette with four semantic lanes.”

### Recommended palette family

#### A. Base world / board

- Midnight navy: `#071321`
- Board slate: `#10263f`
- Raised shell blue: `#183657`
- Text on dark: `#edf3ff`
- Secondary text: `#b7c7e4`

Use for:

- board surroundings
- default neutral panels
- non-urgent chips
- page background

#### B. Decision / prompt / spotlight

- Soft amber: `#f3c86a`
- Deep gold: `#d69b2d`
- Warm parchment tint: `#f5e6b8`

Use for:

- prompt header/timer
- selected choice glow
- urgent “you must act” surfaces
- reveal/highlight headers

#### C. Economy / result semantics

- Gain green: `#47c78a`
- Spend/risk red: `#d7646e`
- Neutral resource cyan: `#69c8ff`

Use for:

- gain/loss numbers
- legal/illegal affordance hints
- rent/purchase/result chips
- score/resource deltas

#### D. Stable per-player accents

- P1 ember orange: `#f48a3d`
- P2 sky cyan: `#58c8ff`
- P3 violet: `#b28cff`
- P4 jade: `#68d99a`

Use for:

- player card rails
- active outline pulse
- marker/ownership ties
- active-character slot accents

### Why this is commercially stronger

This keeps the current dark atmosphere, but adds the same kind of role separation seen in commercial games:

- board and chrome stay cool
- decisions become warm
- outcomes become semantic
- players become memorable by seat color

That is a better fit than making every surface a different hue.

---

## 6. Concrete Improvement Directions

### Priority A. Split “status blue” and “decision gold”

Current issue:

- prompt shell and general status surfaces are too close in tone

Improve by:

- keeping the prompt body dark
- giving the prompt top bar and primary CTA a warmer amber-led treatment
- reserving gold mostly for “act now” and “selected”

Expected result:

- the eye finds the decision surface first

### Priority B. Make the player strip color-led, not text-led

Current issue:

- the strip reads as four similar blue cards with different labels

Improve by:

- adding a seat-color left rail or top accent block
- tinting active/local states with seat color first, badge second
- using icons for seat type and marker ownership where possible

Expected result:

- the player can identify seats in peripheral vision

### Priority C. Reduce tray chrome, increase text fit

Current issue:

- long trick descriptions fight for space inside repeated framed boxes

Improve by:

- removing one chrome layer around the hand/trick tray
- slightly shrinking title/support text before shrinking effect text
- making effect text top-aligned and semantically highlighted
- using stronger line-height control before adding more height

Expected result:

- more cards fit without the tray feeling heavier

### Priority D. Give semantic colors to prompt chips

Current issue:

- target count, owner, timer, cost, and rule context look too similar

Improve by:

- neutral chips for passive context
- amber chips for active decision context
- green/red chips for gain/loss or risk
- seat-color chips when the chip refers to a specific player

Expected result:

- less reading, more scanning

### Priority E. Reserve large text for the dramatic beat

Current issue:

- multiple headings and badges compete at similar visual weight

Improve by:

- letting only one of these be dominant at a time:
  - current prompt title
  - reveal banner
  - major board event

Expected result:

- cleaner turn rhythm

---

## 7. Recommended Implementation Backlog

### P0. Color token refactor

Add semantic CSS variables in `styles.css`:

- `--ui-surface-base`
- `--ui-surface-raised`
- `--ui-surface-decision`
- `--ui-text-primary`
- `--ui-text-secondary`
- `--ui-accent-decision`
- `--ui-accent-success`
- `--ui-accent-danger`
- `--ui-player-1` ~ `--ui-player-4`

Goal:
- stop hardcoding navy/gold variants per component

### P1. Prompt semantic restyle

Targets:

- `PromptOverlay.tsx`
- prompt top bar
- summary pills
- primary action button

Goal:
- make the prompt feel visually warmer and more obviously actionable than the rest of the HUD

### P1. Player strip identity upgrade

Targets:

- `App.tsx` match player strip
- `styles.css` player card rules

Goal:
- each seat should be recognized by color in under a second

### P1. Trick tray density cleanup

Targets:

- trick tray header typography
- tray chrome removal
- description line-height and size rules

Goal:
- improve fit before increasing vertical budget

### P2. Event/result semantic color pass

Targets:

- turn reveal banners
- economy/result labels
- future event feed rows

Goal:
- make gain/loss/risk legible without extra words

---

## 8. Final Recommendation

The current direction should **not** restart from zero.

The better move is:

1. keep the current board-first structure
2. keep the latest prompt and player-strip compaction work
3. upgrade the visual system from one-tone navy to commercial semantic zoning
4. use benchmark-inspired seat colors and action/economy semantics

In short:

**layout stability should continue from the current implementation, but color hierarchy should move noticeably closer to commercial board/card hybrids.**

---

## Sources

- [Nintendo: Mario Party Superstars official page](https://www.nintendo.com/us/store/products/mario-party-superstars-switch/)
- [Steam: Dokapon Kingdom: Connect](https://store.steampowered.com/app/2338140/Dokapon_Kingdom_Connect/)
- [Steam: 100% Orange Juice](https://store.steampowered.com/app/282800/100_Orange_Juice/)
- [Steam: Balatro](https://store.steampowered.com/app/2379780/Balatro)
- [Steam: Cobalt Core](https://store.steampowered.com/app/2179850/Cobalt_Core/)

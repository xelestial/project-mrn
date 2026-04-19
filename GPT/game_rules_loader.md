# game_rules_loader.py

Loads and saves external JSON rulesets for `GameRules`.

## Responsibilities
- Parse JSON ruleset files into `GameRules`
- Export `GameRules` back to JSON
- Provide a stable external contract for rule injection experiments

## Supported top-level sections
- `token`
- `lap_reward`
- `takeover`
- `force_sale`
- `end`


## 0.7.60 note
The ruleset loader now reads and writes `economy`, `resources`, `dice`, and `special_tiles` sections in addition to token/lap/takeover/force_sale/end.


### 0.7.61 ruleset schema
`economy.land_profiles` is now loaded from JSON and becomes the authoritative numeric source for land purchase/rent values.

### 0.7.62 path resolution
Relative ruleset file paths now resolve from the module directory when the caller runs from a different working directory.

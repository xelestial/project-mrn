# Balance Change Record

- Date: `2026-03-27`
- Scope: `GPT`
- Rule area: `Fortune card / 무뢰 interaction`

## Changed Rule

- Card: `남 좋은 일`
- Previous implementation:
  - If the drawer was `무뢰`, all other players paid `4냥` to the drawer.
  - Otherwise, all other non-`무뢰` players gained `4냥`.
- New implementation:
  - The drawer is excluded.
  - All other alive players simply gain `4냥`.
  - `무뢰` 여부와 무관하게 동일하게 처리한다.

## Reason

- The existing implementation did not match the intended card meaning discussed during balance review.
- The special `무뢰` inversion created off-turn bankruptcies that were interpreted as a rules mismatch rather than intended gameplay.

## Expected Impact

- Removes the hidden punish/steal branch tied to `무뢰`.
- Makes `남 좋은 일` easier to reason about from card text alone.
- Reduces confusing off-turn deaths caused by the previous special-case implementation.

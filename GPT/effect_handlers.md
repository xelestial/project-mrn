Default effect handlers registered by GameEngine.

These handlers preserve existing game rules while moving effect bodies behind event dispatch boundaries, so the engine can emit semantic events instead of owning every effect implementation inline.


Update 0.7.48: landing effects for F/S/MALICIOUS/unowned/own-tile landings are now dispatched through event handlers.

- v0.7.49: added handlers for `fortune.card.apply`, `fortune.movement.resolve`, and `game.end.evaluate`.

## 2026-04-29 fortune action producer note
- The default fortune draw handler now calls `GameEngine._produce_fortune_card_actions()` so built-in movement fortune cards produce queued follow-up actions instead of resolving target movement inline.
- `fortune.card.apply` and `fortune.movement.resolve` remain available for direct compatibility hooks, but the built-in fortune-tile path uses the action producer so Redis checkpoints can resume between fortune draw, queued movement, and arrival.
- Custom integrations that need queued movement should use `fortune.card.produce` and return `QUEUE_TARGET_MOVE`; the engine converts that producer result into a serializable action envelope.
- Backward takeover fortune cards are split into queued movement plus a separate ownership-resolution action.


## 0.7.57 purchase-time token placement
- `handle_purchase_attempt` places at most 1 hand coin on the purchased tile when first-purchase placement is enabled.
- Purchase decision logic now delegates to `GameEngine._resolve_purchase_tile_decision()` so queued `request_purchase_tile` actions and legacy landing purchase handlers share one mutation path.
- takeover keeps placed coins with the tile.
- force sale returns placed coins to the original owner hand.


## v7.61 fleader hotfix
- `handle_marker_flip()` now skips marker flip decisions when the pending marker owner is dead, clearing the pending state instead of asking the policy to evaluate a dead owner.


## v7.61 forensic patch notes
- F tile and trick-driven F changes now emit explicit `reason` and `source` in action logs.


## 최근 메모
- 사기꾼 인수 시도는 이제 정책의 생존 게이트를 통과할 때만 실행된다. 요구 비용을 지불한 뒤에도 2턴 생존 reserve를 유지해야 하며, 고가 인수선(대략 20~24+)은 리더 마감권이 아니면 차단한다.

- 최신 변경: `중매꾼`은 토지 구매(착지 매입) 시 조각 1개가 필요하며, 성공 시 조각 1개를 추가로 소비한다. 조각이 없으면 구매는 실패 처리된다.


- 최신 규칙: `중매꾼`은 인접 추가 매입 시에만 조각 1개를 소모한다. `건설업자`는 기본 착지 매입에서 조각 소모 없이 무료 건설을 한다.

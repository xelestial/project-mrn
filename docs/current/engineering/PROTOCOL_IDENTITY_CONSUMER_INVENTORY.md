# Protocol Identity Consumer Inventory

Date: 2026-05-14

Source plan: `docs/current/planning/PLAN_RUNTIME_PROTOCOL_STABILITY_AND_IDENTITY.md`

This inventory exists because numeric `player_id` still has three different
meanings in the current system:

- Internal engine actor index: allowed inside engine/runtime adaptation.
- Compatibility alias: allowed at protocol/tool boundaries only while public
  identity fields are additive.
- Display/debug label input: allowed for `P1`-style labels, replay summaries,
  and audit grouping.

Do not remove numeric aliases until this inventory has no `compat alias` entries.
Removing numeric fields before that point would break known protocol consumers
instead of completing the identity migration.

## Classification

- `display`: the numeric value is used only for labels, summaries, replay rows,
  latency grouping, or audit output. It is not the public identity contract.
- `engine bridge`: the numeric value is needed to adapt a public protocol
  identity back to the current engine seat/player index.
- `compat alias`: the numeric value crosses a protocol, tool, schema, or API
  boundary for compatibility while public identity companions are introduced.
- `protocol violation`: the numeric value is being used as public identity
  without a public companion field or an explicit bridge justification.

Current `protocol violation` entries: none found.

## Consumer Inventory

| Consumer | Classification | Evidence | Removal condition |
| --- | --- | --- | --- |
| `apps/web/src/domain/stream/decisionProtocol.ts` | `compat alias` | `buildDecisionMessage()` can send a public string `player_id`, but it still carries `legacy_player_id`, numeric `missing_player_ids`, numeric `resume_tokens_by_player_id`, and numeric `prompt_instance_id` companions. | Outbound decision contracts and all receivers must accept public identity as primary and consume numeric values only from explicit legacy fields. |
| `apps/web/src/hooks/useGameStream.ts` | `compat alias` | UI decision submission passes `playerId`, `legacyPlayerId`, `publicPlayerId`, `seatId`, and `viewerId` into the decision message. Duplicate-flight keys now prefer public/protocol identity and no longer require a numeric legacy bridge when a public identity companion is present, while numeric ids remain accepted for legacy prompts. Rendered UI prompt actionability now compares `LocalViewerIdentity` public/protocol/viewer/seat identity against `PromptViewModel.identity` before legacy fallback. | The remaining actionable prompt view-model construction and display selectors must no longer require a numeric local player id before this can move out of `compat alias`. |
| `apps/web/src/domain/viewer/localViewerIdentity.ts` | `engine bridge` | `LocalViewerIdentity` separates `view_commit.viewer` public/protocol companions from the numeric `legacyPlayerId`; token and join-response inputs are treated as legacy fallback sources only. `App.tsx` uses the public/protocol/viewer/seat fields for prompt actionability and resolves `effectivePlayerId` from this model for existing display/engine-bridge selectors. | Remaining selectors must use public/protocol identity directly, leaving numeric `legacyPlayerId` only at the engine adapter boundary or display labels. |
| `apps/web/src/headless/HeadlessGameClient.ts` | `compat alias` | Headless decisions now send public `player_id` when available, expose `HeadlessDecisionContext.identity.primaryPlayerId` to policies, and write compact decision/view traces with `primary_player_id` plus explicit legacy/public companions. Top-level trace `player_id` and internal prompt matching still use the numeric player seat value for compatibility. | Headless routing, duplicate suppression, retry matching, and top-level trace keys must no longer require numeric `player_id` when public identity companions are present. |
| `apps/web/src/headless/httpDecisionPolicy.ts` | `compat alias` | `HttpDecisionPolicyRequest` now exposes `identity.primary_player_id` and `primary_player_id_source` so HTTP policy consumers can use public identity as the primary request identity while numeric `player_id` and `legacy_player_id` remain compatibility aliases. | Policy consumers must stop reading top-level numeric `player_id` as primary identity; only then can the numeric alias move to an explicit legacy/debug-only field or be removed from this request. |
| `apps/web/src/headless/protocolReplay.ts` | `display` | Replay rows use numeric `player_id` to group observations, rewards, final rank, and historical summaries while preserving public identity companions where available. | No protocol removal blocker, but replay exports should label the field as legacy/display if public identity becomes the primary export key. |
| `apps/web/src/headless/fullStackProtocolHarness.ts` | `display` | The harness keeps joined seat numbers and latency trace `player_id` values for progress, grouping, and operator evidence. | No protocol removal blocker if harness output remains display-only or moves to public identity labels. |
| `apps/web/src/domain/selectors/streamSelectors.ts` | `display` | Stream selectors derive actor labels, player cards, board ownership labels, and prompt actor labels from numeric player fields. | No protocol removal blocker if display labels keep using `seat_index`/`player_label` or explicit legacy fields. |
| `apps/web/src/domain/selectors/promptSelectors.ts` | `engine bridge` | `promptIdentityFromActivePromptPayload()` now projects public/protocol/legacy prompt target identity into an explicit `PromptIdentityViewModel`, and `PromptViewModel.identity.primaryPlayerId` prefers public identity. `isPromptTargetedToIdentity()` compares public player, protocol player, viewer, and seat identity before legacy numeric fallback; `promptPrimaryTargetId()` and `isPromptPrimaryTarget()` keep queued-prompt target checks on that identity model instead of direct top-level `PromptViewModel.playerId` comparisons. Rendering still requires a numeric `legacy_player_id` bridge before building the actionable prompt view model. | Actionable prompt view-model construction must no longer require the numeric legacy bridge before this can move out of `engine bridge`. |
| `packages/runtime-contracts/ws/schemas/outbound.decision.schema.json` | `compat alias` | The outbound decision schema now accepts public string `player_id` and explicit public companions, while still accepting numeric `player_id` for compatibility. | All outbound decision producers and receivers must stop depending on numeric `player_id` as the primary identity. |
| `packages/runtime-contracts/ws/schemas/inbound.prompt.schema.json` | `compat alias` | The inbound prompt schema now accepts public string payload `player_id` and explicit public companions, while still accepting numeric `player_id` for compatibility. | Prompt producers and consumers must make public prompt target identity primary and use numeric identity only as an explicit legacy companion. |
| `packages/runtime-contracts/external-ai/schemas/request.schema.json` | `compat alias` | The external AI decision request schema now accepts public string `player_id` and explicit public companions, while still accepting numeric `player_id` for compatibility. | External worker requests must use public identity fields as primary, with numeric `player_id` retained only under a legacy compatibility name if still needed. |
| `tools/scripts/external_ai_full_stack_smoke.py` | `compat alias` | The smoke worker request and callback payload now copy pending prompt request/player/seat/viewer companions while retaining numeric `player_id` and `legacy_player_id` for compatibility. | The smoke script can drop numeric decision identity only after the external-AI callback route and worker request contract no longer need numeric aliases. |
| `tools/scripts/redis_restart_smoke.py` | `compat alias` | The restart smoke can find prompts when protocol `player_id` is public and `legacy_player_id` carries the numeric bridge; decision payloads preserve request/player/seat/viewer companions while retaining numeric aliases for compatibility. | Restart smoke can drop numeric decision identity only after replay prompt lookup and WebSocket decision submission no longer need numeric legacy bridge inputs. |
| `tools/scripts/game_debug_log_audit.py` | `display` | The audit groups duplicate decisions and prompt lifecycles by `session_id`, `player_id`, and `request_id` to produce human-readable findings. | No protocol removal blocker if audit grouping switches to public identity or labels numeric values as legacy/display. |

## Removal Gates

1. Runtime contract schemas stop requiring numeric `player_id` as the public
   identity field.
2. Browser, headless, external-AI, and smoke decision submitters can send a
   decision without a numeric public `player_id` when public identity companions
   are present.
3. Prompt selection keeps the engine bridge at one explicit adapter boundary
   instead of requiring protocol payload consumers to infer numeric identity.
4. Replay, harness, and audit outputs either use public identity keys or mark
   numeric values as display/legacy-only.
5. This inventory is updated until no `compat alias` entries remain; only then
   can numeric alias removal be treated as a protocol cleanup instead of a
   breaking migration.

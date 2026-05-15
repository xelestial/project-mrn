# Implementation Journal

This journal is current-state context, not an exhaustive historical log. Keep
entries only when they help a future implementation session decide:

- what changed recently,
- what responsibility moved or intentionally stayed,
- what verification already proved,
- what remaining work should be picked next.

Older detailed phase logs should be removed once their conclusions are reflected
in the active plans, status index, tests, or canonical contract documents.

## 2026-05-15 Active Prompt View-State Primary-Only Publish

- `build_prompt_view_state()` no longer emits top-level `player_id` for
  public/protocol active prompts. It publishes `primary_player_id`,
  `primary_player_id_source`, `public_player_id`, `seat_id`, `viewer_id`, and
  explicit `legacy_player_id` instead.
- Legacy-only numeric active prompts still emit numeric `player_id` with
  `player_id_alias_role: "legacy_compatibility_alias"`.
- `promptViewModelFromActivePromptPayload()` can now build a prompt view model
  from primary/public identity companions even when top-level active-prompt
  `player_id` is absent.
- The nested `view_state.prompt.active` payload in
  `inbound.prompt.public_identity.json` now freezes the primary-only active
  prompt shape. The top-level prompt payload in that same example remains
  public-top-level compatibility evidence.

Responsibility result: active prompt view-state projection moved off public
top-level `player_id` production. Pending prompt storage, `PromptService`
numeric routing, outbound decision submit shape, and engine continuation maps
remain unchanged.

## 2026-05-15 Decision ACK Primary-Only Publish

- `build_decision_ack_payload()` now calls the shared public-primary wire helper
  with `omit_player_id_for_public=True` when public identity companions are
  present.
- WebSocket and external-AI callback ACK producers now publish
  `primary_player_id`, `primary_player_id_source`, `public_player_id`,
  `seat_id`, `viewer_id`, and `legacy_player_id` without top-level
  `player_id` for public/protocol identity.
- Legacy-only ACKs still emit numeric `player_id` with
  `player_id_alias_role: "legacy_compatibility_alias"`.
- Frozen accepted/rejected ACK examples now match the current primary-only
  producer shape; `inbound.decision_ack.public_identity.json` remains schema
  compatibility evidence for older public top-level ACKs.

Responsibility result: ACK payload construction moved from public top-level
`player_id` production to primary-only public production. Decision submission,
PromptService numeric routing, and legacy-only ACK compatibility did not move.

## 2026-05-15 Runtime Prompt Primary-Only Publish

- Runtime prompt publishing now calls `public_primary_player_wire_payload()` with
  `omit_player_id_for_public=True` for WebSocket `prompt` messages and paired
  `decision_requested` events when public identity companions are present.
- The helper default still emits public top-level `player_id`; prompt and ACK
  producers opt into primary-only publishing deliberately at their own
  boundaries.
- Added stream read-outbox coverage proving a primary-only prompt still routes to
  the authorized public/seat/viewer identity and remains hidden from other seats
  and spectators.
- Updated the frozen external-AI `decision_requested` event example to match the
  primary-only runtime prompt publish shape.

Responsibility result: runtime prompt publishing now owns the primary-only public
wire shape for prompt and decision-request delivery. Pending prompt storage and
engine numeric routing remain unchanged.

## 2026-05-15 WS Prompt Primary-Only Fixture

- Added frozen `inbound.prompt.primary_identity.json` so the WebSocket contract
  package has a prompt example identified by `primary_player_id`,
  `primary_player_id_source`, `public_player_id`, `seat_id`, and `viewer_id`
  without payload `player_id`.
- Updated `inbound.prompt.schema.json` so payload `player_id` is one accepted
  identity channel rather than the mandatory channel. Identity-less prompt
  payloads remain invalid, and numeric `player_id` still requires explicit
  legacy alias metadata.
- `inbound.prompt.public_identity.json` remains public top-level prompt
  compatibility evidence; its nested active view-state is now superseded by the
  primary-only active prompt shape documented above. Numeric prompt examples
  remain compatibility evidence.

Responsibility result: WebSocket runtime contracts now own primary-only prompt
fixture evidence. Runtime prompt producers and client consumers did not move in
this slice.

## 2026-05-15 WS Decision ACK Primary-Only Fixture

- Added frozen `inbound.decision_ack.primary_identity.json` so the WebSocket
  contract package has an ACK example identified by `primary_player_id`,
  `primary_player_id_source`, `public_player_id`, `seat_id`, and `viewer_id`
  without payload `player_id`.
- Updated `inbound.decision_ack.schema.json` so payload `player_id` is one
  accepted identity channel rather than the mandatory channel. Identity-less
  ACK payloads remain invalid, and numeric `player_id` still requires explicit
  legacy alias metadata.
- `inbound.decision_ack.public_identity.json` remains the public top-level ACK
  example, and numeric ACK examples remain compatibility evidence.

Responsibility result: WebSocket runtime contracts now own primary-only ACK
fixture evidence. Runtime ACK producers and client consumers did not move in
this slice.

## 2026-05-15 WS Decision Primary-Only Fixture

- Added frozen `outbound.decision.primary_identity.json` so the WebSocket
  contract package now carries a file-level example of an outbound decision
  identified by `primary_player_id`, `primary_player_id_source`,
  `public_player_id`, `seat_id`, and `viewer_id` without top-level `player_id`.
- `outbound.decision.public_identity.json` remains the public top-level identity
  example, and `outbound.decision.movement_roll.json` remains the labeled
  numeric compatibility example.

Responsibility result: WebSocket runtime contracts now own primary-only
outbound decision fixture evidence. Runtime producers and receivers did not
move in this slice.

## 2026-05-15 External-AI Request Example Primary-Only Identity

- Frozen external-AI `request.*.json` examples no longer include public
  top-level `player_id`.
- The examples now represent the preferred request identity through
  `primary_player_id`, `primary_player_id_source`, `public_player_id`,
  `seat_id`, and `viewer_id`, with `legacy_player_id` retained as the explicit
  numeric bridge.
- Schema tests still cover public top-level `player_id` and labeled numeric
  aliases as compatibility input, so this changes the representative examples,
  not the accepted migration surface.

Responsibility result: runtime contract examples stopped teaching public
top-level `player_id` as the primary external-AI request identity. Worker
schema compatibility and server callback normalization did not move.

## 2026-05-15 External-AI Smoke Worker/Callback Primary-Only Identity

- `external_ai_full_stack_smoke.py` no longer sends top-level `player_id` to
  the worker `/decide` request or server callback body when the pending prompt
  exposes public/protocol primary identity or public player companions.
- The worker request and callback body still carry `primary_player_id`,
  `primary_player_id_source`, `legacy_player_id`, and public/seat/viewer
  companions, so both protocol edges remain identifiable through the server
  callback route's canonical identity adapter.
- Legacy-only pending prompts still produce numeric worker/callback `player_id`
  plus `player_id_alias_role`.

Responsibility result: smoke worker request and callback production moved off
public top-level `player_id`. Server callback routing, prompt submission, and
engine numeric bridges did not move.

## 2026-05-15 External-AI Worker Primary-Only Identity

- `ExternalAiDecisionRequest` no longer requires top-level `player_id` when a
  request carries explicit `primary_player_id` plus source, `public_player_id`,
  `seat_id`, or `viewer_id`.
- The worker API still rejects identity-less requests and blank identity
  strings. Numeric `player_id` remains accepted only through the existing
  compatibility validation.
- The external-AI request contract schema now matches the worker input boundary:
  `player_id` is one allowed identity channel, not the mandatory canonical
  field.

Responsibility result: the worker request acceptance boundary moved off a
mandatory top-level `player_id`. Worker choice logic, server callback routing,
`PromptService`, and the engine numeric bridge did not move.

## 2026-05-15 WS Decision Contract Primary-Only Identity

- `outbound.decision.schema.json` no longer requires top-level `player_id` when
  a decision carries explicit `primary_player_id` plus source, `public_player_id`,
  `seat_id`, or `viewer_id`.
- The schema still rejects decision messages with no player identity channel,
  and numeric top-level `player_id` remains accepted only as a labeled legacy
  compatibility alias with primary/source/legacy metadata.
- The runtime contract test helper now evaluates `anyOf`, so this identity
  requirement is actually enforced by the schema tests instead of being silently
  ignored by the local subset validator.

Responsibility result: the WebSocket contract moved to match the already
implemented route adapter boundary. External-AI worker request optionalization
moved later as a separate compatibility boundary.

## 2026-05-15 Inbound Primary Identity Adapter

- `SessionService.resolve_protocol_player_id()` now accepts explicit
  `primary_player_id` plus `primary_player_id_source` as inbound decision
  identity. Public/protocol primary ids resolve through the public player id;
  legacy primary ids resolve through the numeric seat bridge.
- The WebSocket decision route and external-AI decision callback pass those
  fields into the resolver, then normalize the accepted request back to the
  internal numeric `player_id`/`legacy_player_id` shape before calling
  `PromptService`.
- Route-level regression tests now verify malformed explicit primary identity
  pairs, such as numeric `primary_player_id` with source `public`, fail through
  the existing `PLAYER_MISMATCH` path instead of being repaired by a numeric
  alias.

Responsibility result: inbound protocol identity interpretation remains in the
single `SessionService` adapter. Route handlers do not duplicate public primary
identity into alternate fields, and `PromptService` still receives the numeric
engine bridge required by prompt/runtime continuation.

## 2026-05-15 Prompt Choice Payload Identity Guard

- `PromptService.submit_decision()` now rejects a submitted `choice_payload`
  whose target legacy/public/seat/viewer identity contradicts the selected
  pending legal choice `value`.
- The guard runs before command materialization, so a client cannot select one
  `choice_id` while sending a payload that targets another player.
- The protocol identity inventory now separates this closed semantic guard from
  the still-intentional numeric engine bridge for command parsing and module
  continuation.

Responsibility result: selected choice target identity consistency is owned by
the prompt command materialization boundary. Submitted `choice_payload` is not
rewritten; unrelated payload fields, engine decision parsing, and numeric target
bridge compatibility did not move.

## 2026-05-15 Prompt Choice Payload Command Materialization

- `PromptService.submit_decision()` now materializes the selected pending legal
  choice `value` into accepted decision command `choice_payload` when the
  submitted decision only carries `choice_id`.
- Target-choice companions produced at the runtime prompt boundary therefore
  continue into the command payload and nested decision payload without
  requiring a client echo.

Responsibility result: selected raw choice value propagation moved into the
prompt command materialization boundary. Existing submitted `choice_payload`
compatibility, `choice_id` validation, engine decision parsing, and numeric
target bridge fields did not move.

## 2026-05-15 Runtime Target Choice Identity Materialization

- `RuntimeService._materialize_prompt_boundary_sync()` now enriches legal
  choice `value.target_player_id` payloads with authoritative target
  legacy/public/seat/viewer companions before writing the pending prompt.
- The same enriched payload is then used by the runtime prompt publish boundary,
  so WebSocket prompt consumers and external worker inputs can read target
  public identity without inferring it from the numeric target bridge.

Responsibility result: session-owned target identity materialization moved to
the runtime prompt materialize boundary. Engine choice construction,
`choice_id`, decision parsing, and numeric `target_player_id` compatibility did
not move.

## 2026-05-15 Headless Trace Alias Role Boundary

- `HeadlessTraceEvent` now labels top-level numeric trace `player_id` as
  `player_id_alias_role: "legacy_debug_alias"` through the shared
  `recordTrace()` path.
- Public/protocol `primary_player_id` and companion fields remain the primary
  identity for trace consumers.

Responsibility result: trace producer output now explicitly owns alias
classification. Numeric trace `player_id` remains compatibility/debug data;
WebSocket protocol, server runtime routing, and replay output shape did not
move.

## 2026-05-15 Stream View-State Actor Bridge Review

- `streamSelectors.ts` now resolves view-state turn-stage actors, scene
  situation actors, theater/core feed actors, and `mark_target` candidates from
  explicit `*_legacy_player_id` or `*_seat_index` companions before falling
  back to raw `*_player_id` aliases.
- Added selector coverage where the raw view-state actor and mark-target
  `player_id` fields are public/protocol strings while explicit legacy/public
  companions carry the temporary display bridge.

Responsibility result: actor and mark-target display labels are now owned by
the selector companion adapter instead of requiring raw view-state `player_id`
aliases to stay numeric. Runtime and engine numeric actor ownership did not
move.

## 2026-05-15 Runtime Prompt Public Primary Publish Boundary

- `public_primary_player_wire_payload()` now owns the shared public-primary
  wire conversion for server prompt and ACK producers.
- Runtime prompt publishing uses that conversion for both the private
  WebSocket `prompt` message and the paired `decision_requested` event when
  `public_player_id` is available. The wire payload exposes string top-level
  `player_id`, keeps the numeric seat as `legacy_player_id`, and removes the
  legacy alias label from the public-primary shape.
- `PromptService` pending prompts still store numeric `player_id` for internal
  lifecycle, wait, and command routing.

Responsibility result: public protocol payload shape now belongs to the
publish boundary; numeric routing responsibility intentionally remains inside
the prompt lifecycle and engine bridge.

## 2026-05-15 Stream Display Identity Companion Fallback

- `streamSelectors.ts` prompt/decision actor display now reads explicit
  `player_label`, `legacy_player_id`, and `seat_index` companions before
  falling back to numeric `player_id`. Public/protocol string `player_id`
  therefore no longer renders prompt or `decision_requested` fallback details
  as `-` when display companions are present.
- This is deliberately a display-boundary fix. Board ownership, player cards,
  turn-history participant ids, and other engine bridge fields remain numeric
  until their own compatibility boundaries are removed.

Responsibility result: stream selector label derivation owns the companion
fallback needed for display; protocol/runtime identity ownership did not move.

## 2026-05-15 UI Decision Flight Identity Repair

- `resolveDecisionFlightIdentity()` now rejects numeric explicit primary ids
  when the declared source is `public` or `protocol`, matching the outbound
  decision builder and schema rules.
- Added coverage for malformed public primary input where `primaryPlayerId` is
  numeric but `publicPlayerId` is available; duplicate-flight keys now use the
  public identity instead of recording the numeric alias as a public primary.

Responsibility result: UI duplicate suppression and debug evidence now share
the same primary identity interpretation as outbound decision serialization.
Numeric ids remain valid only for explicit legacy decision flight identity.

## 2026-05-15 HTTP Policy Player Summary Legacy Bridge

- `HttpDecisionPolicyRequest.player_summary` now finds compact player rows by
  explicit `legacy_player_id` first, then numeric legacy `player_id`, instead
  of requiring `view_state.players.items[].player_id` to stay numeric.
- Added coverage for future-compatible view-state rows where `player_id` is a
  public/protocol string and the numeric compatibility value is carried only by
  `legacy_player_id`.

Responsibility result: the HTTP decision policy request still sends
public/protocol identity as primary, while the compact summary boundary now owns
the temporary numeric bridge needed to attach projected player stats.

## 2026-05-15 Headless Harness Join Identity Bridge

- `joinProtocolSeats()` now treats a string join-response `player_id` as a
  public/protocol identity value, not as a number to coerce. The temporary
  numeric `ProtocolSeatJoin.playerId` bridge is resolved only from explicit
  `legacy_player_id`, a numeric legacy `player_id`, or the joined seat fallback.
- Added harness coverage for the future-compatible case where the join response
  supplies string public `player_id` plus explicit legacy/public/seat/viewer
  companions.

Responsibility result: headless protocol runs still use numeric client grouping
internally, but the numeric bridge is now materialized at the harness join
boundary instead of being inferred from arbitrary protocol `player_id` strings.

## 2026-05-15 Frontend Transport Prompt Instance Companion

- `FrontendTransportAdapter` serialization coverage now verifies that outbound
  decisions preserve `public_prompt_instance_id` next to the numeric
  `prompt_instance_id` lifecycle bridge when using the same stream protocol as
  the browser frontend.
- The protocol identity inventory now lists the frontend transport adapter as a
  compatibility boundary instead of hiding it behind the shared decision
  builder.

Responsibility result: prompt lifecycle ownership did not move. The transport
adapter now has explicit evidence responsibility for carrying the public prompt
instance companion through the WebSocket serialization boundary; numeric
`prompt_instance_id` remains the internal resume/lifecycle bridge.

## 2026-05-15 Redis Inspector Prompt Identity Companions

- `RedisStateInspector` compact prompt and outbox summaries now preserve public
  prompt/request/player identity companions next to the numeric
  `prompt_instance_id` lifecycle bridge and numeric legacy `player_id`.
- Inspector coverage now locks that active runtime prompts plus pending and
  lifecycle prompt records expose `public_prompt_instance_id`,
  `primary_player_id`, and related companions from Redis state.

Responsibility result: operator/debug prompt inspection moved away from
numeric-only prompt identity evidence. Runtime resume and module continuation
still own numeric `prompt_instance_id` as the internal lifecycle bridge.

## 2026-05-15 External AI Smoke Identity Summary

- `external_ai_full_stack_smoke.py` now includes `primary_player_id`,
  `primary_player_id_source`, and request/player/seat/viewer companions in the
  returned `pending_prompt` summary. The raw pending `player_id` is still shown,
  but it is no longer the only visible identity in operator evidence.
- Added smoke-script coverage for the mixed migration case where raw
  `player_id` is a numeric legacy alias and explicit public primary identity is
  available.

Responsibility result: external-AI smoke reporting moved off bare raw
`pending_prompt.player_id` evidence. Worker/callback protocol adaptation remains
owned by the smoke helper, and numeric legacy aliases intentionally remain for
legacy-only prompt input.

## 2026-05-15 External AI Target Choice Identity Preference

- External AI worker selection policy now honors `preferred_target_public_player_id`,
  `preferred_target_seat_id`, and `preferred_target_viewer_id` for `mark_target`
  and `doctrine_relief` choices before falling back to the legacy numeric
  `preferred_target_player_id`. The priority-scored adapter uses the same
  target identity preference before score fallback on these target-choice
  surfaces.
- Runtime contract examples for external-AI `mark_target` now show target
  legacy/public/seat/viewer companion fields inside raw choice payloads. The
  raw payload is still echoed unchanged; this change only moves target-choice
  preference responsibility into the worker policy adapter.

## 2026-05-15 Prompt Choice Target Identity Surface

- `mark_target` and `doctrine_relief` prompt surfaces now preserve target
  identity companions (`target_legacy_player_id`, `target_public_player_id`,
  `target_seat_id`, `target_viewer_id`) in server view-state projection and
  frontend selector parsing. The legacy numeric `target_player_id` remains as
  the engine bridge, and raw choice `value` payloads are not rewritten.
- Shared selector fixture coverage for `doctrine_relief` now exercises the
  target companion contract. Targeted server and frontend selector tests verify
  both choice surfaces keep the public/seat/viewer companions available to
  display/protocol consumers.

## 2026-05-15 Runtime Contract Primary Identity Guard

- Runtime contract schemas now reject numeric `primary_player_id` when
  `primary_player_id_source` is `public` or `protocol`, and reject string
  `primary_player_id` when the source is `legacy`, across WebSocket outbound
  decisions, inbound prompts, inbound decision ACKs, and external-AI request
  payloads. This moves the malformed-primary guard from producer-local cleanup
  into the shared protocol contract while keeping legacy primary fallback
  numeric-only under `primary_player_id_source: "legacy"`.
- `SessionService.resolve_protocol_player_id()` now treats all supplied public,
  protocol, seat/viewer, and legacy numeric identity fields as one candidate
  set. If those fields resolve to different internal seats, the adapter returns
  no match and the existing route/API mismatch handling rejects the request.
  This keeps the numeric bridge at the server adapter boundary while preventing
  a conflicting legacy alias from silently overriding a public/protocol primary
  identity.
- `PromptService.submit_decision()` now performs the same fail-closed identity
  consistency check at decision acceptance. A decision whose public player,
  seat, viewer, legacy, or primary identity companions contradict the pending
  prompt is rejected before command materialization. The accepted command still
  carries numeric `player_id` as the engine bridge, but that bridge can no
  longer overwrite a contradictory public/protocol identity.

## 2026-05-14 Runtime Protocol Identity Continuation

- Added `PROTOCOL_IDENTITY_CONSUMER_INVENTORY.md` to classify the remaining
  numeric `player_id` consumers before alias removal. The inventory separates
  display-only uses, the current engine bridge, compatibility aliases, and
  protocol violations; current protocol violation entries are none found. The
  explicit removal rule is that numeric aliases stay until the inventory has no
  `compat alias` entries.
- Runtime contract schemas for WebSocket outbound decisions, WebSocket inbound
  prompts, and external-AI decision requests now accept public string
  `player_id` plus explicit `legacy_player_id`, `public_player_id`, `seat_id`,
  and `viewer_id` companions. Existing numeric `player_id` examples remain
  valid; this only removes the schema-level integer-only blocker.
- The WebSocket outbound decision schema now explicitly owns the continuation
  identity companion contract already emitted by frontend decisions and
  accepted by the server: `prompt_instance_id`, `public_prompt_instance_id`,
  prompt fingerprint fields, resume metadata, frame/module/batch fields,
  numeric `missing_player_ids` and `resume_tokens_by_player_id`, plus
  public-player, seat, and viewer companion lists/maps. The outbound decision
  example now exercises that path, so the contract no longer relies on
  `additionalProperties` to hide those fields.
- WebSocket outbound decision construction now exposes `primary_player_id` and
  `primary_player_id_source`, and labels a top-level numeric `player_id` as
  `player_id_alias_role: "legacy_compatibility_alias"`. Public/protocol
  `player_id` values remain primary protocol identities, while numeric-only
  decisions are explicitly marked as the legacy fallback path.
- `PromptService.create_prompt()` and server active prompt view-state now expose
  `primary_player_id`, `primary_player_id_source`, and label numeric top-level
  `player_id` as `player_id_alias_role: "legacy_compatibility_alias"`. The
  frontend prompt selector consumes those explicit primary fields first, then
  keeps the existing public/protocol/legacy fallback path for mixed migration
  payloads.
- Server active prompt view-state now omits top-level `player_id` when the
  source prompt exposes public/protocol identity, while keeping
  `legacy_player_id` as the explicit numeric bridge. `player_id_alias_role` is
  emitted only for legacy-only numeric top-level prompts, so the public prompt
  target is no longer serialized through the numeric active-prompt bridge.
- Server active prompt view-state also preserves complete public-player, seat,
  and viewer batch-continuation companion maps without fabricating numeric
  `missing_player_ids`, `resume_tokens_by_player_id`, or `prompt_instance_id`
  aliases when those aliases are absent from the source prompt. This proves the
  projection layer is not the remaining blocker; the numeric batch bridge stays
  because `PromptService` and the runtime semantic guard still validate numeric
  resume maps before module continuation.
- Module continuation validation now lives in
  `apps/server/src/domain/module_continuation_contract.py`. `PromptService` and
  the runtime semantic guard share that contract for required module resume
  fields, simultaneous batch prompt detection, and numeric batch resume bridge
  validation. This is a responsibility consolidation, not numeric alias removal:
  public-player/seat/viewer companions can exist at projection/protocol
  surfaces, but runtime prompt validation still requires the numeric engine
  bridge before module continuation.
- Frontend decision duplicate-flight keys now prefer `publicPromptInstanceId`
  before the numeric `promptInstanceId` lifecycle alias when no prompt
  fingerprint is present. Decision payloads still send numeric
  `prompt_instance_id`, `missing_player_ids`, and `resume_tokens_by_player_id`
  because the server runtime and engine continuation path still consume those
  explicit bridge fields.
- `PromptService.submit_decision()` now preserves the same primary identity trio
  from the pending prompt into lifecycle decision records, command payloads, and
  nested command decision payloads. This keeps the command boundary from
  silently downgrading an explicit public primary identity back to an unlabeled
  numeric `player_id`.
- `decision_ack` payloads now carry `player_id_alias_role`,
  `primary_player_id`, and `primary_player_id_source` whenever the legacy
  numeric `player_id` remains in the ACK. `SessionService.protocol_identity_fields()`
  supplies the public primary identity for normal session-backed ACKs, and
  `build_decision_ack_payload()` falls back to explicit legacy-primary metadata
  if no public identity companion is available. The WebSocket ACK schema and
  examples now require that primary metadata for numeric ACK aliases.
- The protocol identity consumer inventory already documented the WebSocket
  inbound `decision_ack` schema as a `compat alias` boundary, but the inventory
  integrity test did not require that row. The doc guard now includes the ACK
  schema so this protocol boundary cannot silently disappear from the
  inventory while numeric ACK aliases remain.
- External-AI request contract examples now exercise the public-primary request
  shape: top-level `player_id` is the public string identity,
  `primary_player_id_source` is `public`, and `legacy_player_id`,
  `public_player_id`, `seat_id`, and `viewer_id` are explicit companions.
  Numeric player ids still remain valid as a labeled legacy alias in schema
  tests, but the frozen examples no longer present the numeric alias as the
  canonical external worker contract.
- External-AI request schema tests now separate the canonical public-primary
  sample from the labeled numeric compatibility-alias sample. This keeps the
  compatibility path covered without teaching external worker authors to attach
  `player_id_alias_role` to the normal public string `player_id` request.
- The external-AI full-stack smoke adapter now preserves pending prompt
  `legacy_request_id`, `public_request_id`, `public_prompt_instance_id`,
  `legacy_player_id`, `public_player_id`, `seat_id`, and `viewer_id` through the
  worker request and callback body. It now uses public/protocol top-level
  `player_id` when available and keeps numeric `player_id` plus
  `player_id_alias_role: "legacy_compatibility_alias"` only for legacy-only
  prompt input.
  When a pending prompt already carries explicit `primary_player_id` metadata,
  the worker request and callback now consume that primary identity before
  falling back to `public_player_id`, protocol `player_id`, or legacy numeric
  aliases.
- The Redis restart decision smoke adapter now accepts replay prompts whose
  protocol `player_id` is public as long as `legacy_player_id` or another
  numeric bridge is present. Decision payload construction now preserves the
  same request/player/seat/viewer companions, emits `primary_player_id` and
  `primary_player_id_source`, and uses public/protocol top-level `player_id`
  when available. Numeric top-level `player_id` is labeled as
  `player_id_alias_role: "legacy_compatibility_alias"` only for legacy-only
  prompt input.
- HTTP decision policy requests now use public/protocol top-level `player_id`
  when available and mirror that value in `identity.player_id`. Numeric
  `player_id` plus `player_id_alias_role: "legacy_compatibility_alias"` remains
  only for legacy-only policy input.
- Browser decision serialization, headless HTTP policy requests, external-AI
  smoke worker/callback payloads, and Redis restart smoke decision payloads now
  reject malformed numeric public/protocol `primary_player_id` values when a
  public companion can repair the identity. This keeps top-level decision
  `player_id` public/protocol-first even across mixed migration payloads.
- Headless view-commit trace compaction now consumes explicit active-prompt
  `primary_player_id` plus `primary_player_id_source` before numeric aliases.
  Numeric `active_prompt_player_id` and `active_prompt_protocol_player_id`
  remain trace/debug compatibility fields, not the primary prompt identity.
Responsibility result: ACK primary identity ownership moved to the server ACK
builder/session identity boundary, and HTTP policy request protocol identity is
owned by the request builder. Consumers no longer need to guess whether numeric
ACK or legacy-only HTTP-policy `player_id` values are primary identity or
compatibility aliases.
Runtime contract responsibility also moved: outbound decision continuation
companion fields are now owned by the frozen schema and example instead of
being tolerated only through open-ended `additionalProperties`.
- Runtime fanout and session bootstrap identity helpers now keep explicit
  prefixed/list legacy companions for protocol player-id fields. Examples:
  `acting_legacy_player_id`, `owner_legacy_player_id`,
  `alive_legacy_player_ids`, `marker_owner_legacy_player_id`, and
  `pawn_legacy_player_ids`. Numeric `*_player_id` aliases still remain for
  compatibility; this only makes the companion shape complete while public
  string IDs are additive.
- `domain.protocol_identity.public_identity_numeric_leaks()` now provides a
  reusable recursive guard for protocol payload tests. It fails when public
  identity fields such as `public_player_id`, `seat_id`, `viewer_id`,
  `public_request_id`, `public_prompt_instance_id`, `event_id`, public identity
  lists, or `*_by_public_player_id` map keys collapse to numeric values, while
  allowing explicit numeric compatibility aliases such as `player_id`,
  `legacy_player_id`, `seat`, and `prompt_instance_id`.
- The same guard now runs over representative runtime fanout event payloads,
  fanout snapshots, active simultaneous batch prompt payloads, delayed prompt
  publication payloads, WebSocket decision acks, external-AI callback decision
  records, and admin external-AI pending-prompt rows. This expands the evidence
  net before any future numeric alias removal; it does not remove the
  compatibility aliases.
- Prompt timeout fallback now preserves prompt identity companions through
  fallback execution history and timeout/resolved event publication. The
  canonical `request_id` remains the opaque public id, and
  `legacy_request_id` remains the compatibility/debug alias.
- `PromptBoundaryBuilder` now attaches prompt protocol identity companions at
  boundary construction time. Explicit-request prompts and module continuation
  prompts carry `legacy_request_id`, `public_request_id`, and
  `public_prompt_instance_id` before they reach prompt persistence or gateway
  publication; numeric `prompt_instance_id` remains the compatibility lifecycle
  key.
- Flipped new `PromptService` prompt storage and command-resume payloads to use
  the opaque public request id as the canonical `request_id`.
- Legacy semantic request IDs remain as `legacy_request_id` plus bounded
  in-memory/Redis aliases, so older callbacks and debug lookups still resolve
  to the public canonical key.
- `PromptService` now accepts a submitted `public_request_id` at the protocol
  boundary, preserves it as the canonical prompt key, and accepts submitted
  legacy request IDs as compatibility aliases.
- `DecisionGateway` now switches its local request-id variable to the
  `PromptService` canonical public id after prompt creation/reuse, so prompt
  messages plus requested/resolved/timeout events share the same opaque
  `request_id` while carrying `legacy_request_id` for compatibility.
- Module decision commands now carry explicit `prompt_instance_id`, and runtime
  resume matching and prompt sequence seeding now use that explicit field
  without parsing legacy request-id suffixes for prompt instance recovery.
- Prompt instance sequence increment/restore now lives behind
  `services.prompt_boundary_builder.PromptBoundaryBuilder`, which uses
  `domain.prompt_sequence.PromptInstanceSequencer` for the numeric rule.
  `_ServerDecisionPolicyBridge` owns the builder and recovery seed API;
  `_LocalHumanDecisionClient` no longer exposes prompt sequence state or
  increments prompt instances itself.
- Pending prompt boundary state recording and clearing now also live in
  `domain.prompt_sequence` helpers. `RuntimeService` still detects the
  `PromptRequired` boundary, but the checkpoint fields for pending request,
  prompt type, player, instance id, and sequence advancement are no longer
  hand-written in the transition loop.
- Prompt boundary envelope preparation now runs through
  `PromptBoundaryBuilder`, with the pure merge/copy rule still in
  `domain.prompt_sequence.prepare_prompt_boundary_envelope()`. The builder
  allocates compatibility `prompt_instance_id` values, merges active request
  metadata, and attaches module continuation metadata before the prompt reaches
  `DecisionGateway`.
- Decision-resume prompt sequence matching and post-resume advancement now use
  `domain.prompt_sequence` helpers against the bridge-owned
  `PromptBoundaryBuilder`. The "unknown instance matches", "unseeded sequence
  matches", and `max(current + 1, resume_instance)` rules are no longer
  bridge-local arithmetic or local human client state.
- Active batch prompt enrichment now requires explicit `batch_id` plus
  submitted player identity when exact request-id equality does not match.
  Runtime no longer derives batch identity or player position from the legacy
  `batch:*:pN` request-id shape.
- WebSocket human decision ACKs now include the accepted decision
  `command_seq`, matching the REST/external-AI decision callback boundary and
  letting clients correlate an accepted prompt decision with the queued runtime
  command.
- Admin external-AI pending prompt reads now expose the public canonical
  request id, legacy request alias, public player id, seat id, and viewer id
  while retaining numeric `player_id` as a compatibility routing alias.
- Frontend/headless decision construction now accepts active prompt public
  string `player_id` as the outbound protocol identity. `buildDecisionMessage()`
  carries explicit `legacy_player_id`, `public_player_id`, `seat_id`, and
  `viewer_id` companions, and pure numeric decision messages remain unchanged.
  Active prompt selection only accepts a string protocol `player_id` when the
  payload also carries a numeric `legacy_player_id`, preserving the current
  engine/seat bridge instead of guessing from public IDs.
- The rendered React UI prompt submission path now uses the same active-prompt
  protocol identity extraction as headless. `App.tsx` passes public player,
  legacy player, seat, and viewer companions into `useGameStream.sendDecision()`;
  `useGameStream` now resolves duplicate-flight keys through public/protocol
  identity when present and falls back to numeric identity only for legacy
  prompts.
- The same React UI path now preserves explicit `PromptViewModel.primaryPlayerId`
  plus `primaryPlayerIdSource` through `App.tsx`, `useGameStream`, and
  `buildDecisionMessage()`. Browser decision messages and duplicate-flight keys
  prefer that server-issued prompt primary identity before recomputing from
  public, protocol, or legacy fallback fields.
- `promptSelectors` now exposes an explicit `PromptIdentityViewModel` on
  `PromptViewModel.identity`. The selector can parse public prompt identity
  before the UI resolves it to a legacy engine seat; later prompt display work
  also exposes the same primary identity on `PromptViewModel.primaryPlayerId`.
- `promptSelectors` batch module-continuation completeness is now companion-aware.
  A complete public-player, seat, or viewer missing/resume map is enough to
  construct the batch prompt view model even when numeric continuation maps are
  absent from the selector input. Numeric continuation maps remain parsed as the
  engine bridge, and server runtime remains responsible for materializing that
  bridge before `PromptService` and semantic guard validation.
- `App.tsx` prompt actionability now compares `LocalViewerIdentity`
  public/protocol/viewer/seat identity against `PromptViewModel.identity`
  before legacy fallback. Queued burden-exchange suppression stays on the
  prompt primary identity helper. The remaining numeric requirement is
  compatibility output and engine-bridge selector input, not prompt target
  comparison itself.
- Headless external-policy and replay exports now preserve public player,
  seat, viewer, and legacy player companions. HTTP decision policy requests
  now use public/protocol `player_id` when available while retaining
  `legacy_player_id` and numeric legacy-only fallback fields. They also expose
  an `identity.primary_player_id` block with `primary_player_id_source`, so HTTP
  policy consumers have a clear public-primary identity field. Compact trace
  payloads and replay rows carry the same companions without changing reward
  calculation's numeric actor-index bridge.
- `HeadlessGameClient` now gives decision policies a
  `HeadlessDecisionContext.identity` object and writes compact decision/view
  trace identity blocks with `primary_player_id`. Public identity is visible as
  the policy/trace primary value while numeric `playerId` remains the legacy
  route/debug bridge for current prompt matching, duplicate suppression, and
  retry handling.
- Session bootstrap identity was aligned with the runtime protocol identity
  migration. `session_start.players`, initial snapshot players, marker owner,
  and starting pawn lists now carry public player, seat, and viewer companion
  fields while retaining numeric compatibility aliases.
- `PromptService.wait_for_decision()` now resolves already-submitted public
  request aliases through lifecycle metadata for both in-memory and Redis
  stores. Zero-timeout missing-decision probes still avoid pending/resolved hash
  scans.
- Public request alias lookup now has an in-memory request alias index and
  Redis prompt-hash alias indexes. Pending-read, accept, wait, lifecycle-read,
  timeout, resolved, and command-replay paths can resolve legacy/public request
  aliases without making legacy semantic IDs the canonical key.
- `PromptService.get_prompt_lifecycle()` now accepts both public and legacy
  request aliases and returns the public-key lifecycle record.
- `PromptService.get_pending_prompt()` now accepts public request aliases for
  active pending prompts. It resolves only against active pending records, so
  completed prompts do not reappear as pending through lifecycle metadata.
- `PromptService.mark_prompt_delivered()` and
  `record_external_decision_result()` now resolve submitted public request
  aliases before lifecycle writes, and `PromptService.expire_prompt()` resolves
  active pending aliases before deletion/resolution. Delivered, external-result,
  and expired states therefore update the same legacy-key lifecycle record
  instead of creating or missing a parallel public-key record.
- Redis-backed `PromptService` coverage now proves the same public request
  alias adapter at pending-read, accept, wait, lifecycle-read, and expire
  boundaries. That keeps the Redis path aligned with the in-memory service
  tests instead of relying on one backend's behavior as evidence for both.
- Decision command materialization now copies prompt player identity companions
  (`public_player_id`, `seat_id`, `viewer_id`, and display aliases) into normal
  decision commands, simultaneous batch collector responses, and timeout
  fallback responses. Numeric `player_id` remains the compatibility routing
  alias.
- `BatchCollector` completion commands now expose
  `responses_by_public_player_id` and ordered `expected_public_player_ids` as
  additive companions derived from collected response payloads. Numeric
  `responses_by_player_id` and `expected_player_ids` remain the compatibility
  resume map and ordering contract.
- `RuntimeDecisionResume` now accepts public-only `batch_complete`
  `responses_by_public_player_id` payloads by resolving public player IDs
  through `SessionService` and materializing the numeric engine bridge map.
  Legacy numeric `responses_by_player_id` payloads are still accepted.
- `test_public_batch_complete_resume_applies_to_internal_engine_batch` verifies
  that a public-only batch completion command reaches the engine batch by way
  of the runtime bridge. The remaining numeric `responses_by_player_id` map is
  an internal engine actor-index structure, not a public protocol requirement.
- Responsibility moved: prompt continuation matching and prompt
  storage/resume no longer rely first on semantic `request_id` strings.
  Decision event publication also no longer keeps the pre-create legacy id as
  the event key after `PromptService` has assigned a public id.
  Runtime batch resume/enrichment also no longer manufactures `batch_id` from
  request-id suffixes. `PromptService` command materialization now follows the
  same rule; producers must carry explicit batch identity. Public prompt-id
  lookup responsibility moved into the prompt service/store alias indexes.
  Bootstrap event construction now owns additive public identity enrichment
  before runtime fanout starts. Runtime fanout still owns post-start view
  commits. Both bootstrap and fanout helpers now also own complete
  prefixed/list legacy companion enrichment; route consumers should not patch
  those fields after publication. Frontend decision construction now owns the
  protocol outbound identity shape instead of assuming caller numeric
  `playerId` is the wire identity. Rendered UI prompt submission now owns
  extracting protocol identity from `PromptViewModel`, while `useGameStream`
  owns serialization and numeric flight-key compatibility. Headless policy,
  trace, and replay export boundaries now own public identity preservation
  instead of silently reducing those artifacts back to numeric player ids.
  Engine actor indexes remain internal numeric state. Legacy request IDs now
  remain compatibility inputs rather than the canonical storage key.

Verification:

- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -k "fanout_event_payload_adds_actor_public_identity_for_acting_player or fanout_event_payload_adds_prefixed_identity_for_related_players or fanout_event_payload_adds_public_identity_lists_for_player_id_lists or fanout_snapshot_payload_adds_public_identity_companions" -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_sessions_api.py -k "start_replay_session_start_includes_initial_active_faces" -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_stream_api.py::StreamApiTests::test_connect_resends_pending_prompt_to_matching_seat_without_stream_event apps/server/tests/test_stream_api.py::StreamApiTests::test_resume_resends_pending_prompt_created_without_stream_event apps/server/tests/test_stream_api.py::StreamApiTests::test_prompt_timeout_emits_fallback_execution_and_runtime_tracks_history -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_session_service.py apps/server/tests/test_stream_api.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_decision_resume_does_not_derive_batch_id_from_batch_request_id apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_prompt_boundary_enrichment_uses_explicit_batch_and_player_for_opaque_request_id -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_decision_resume_from_batch_complete_command_uses_collected_response apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_decision_resume_from_batch_complete_command_accepts_public_response_map apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_collected_batch_responses_are_applied_before_primary_resume -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_sequence.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_runtime_prompt_boundary_can_publish_after_view_commit_guardrail apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_human_bridge_prompt_sequence_can_resume_from_checkpoint_value apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_module_resume_seeds_prompt_sequence_from_previous_same_module_decision -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_prompt_module_continuation.py::test_local_human_client_prompt_boundary_is_owned_by_builder apps/server/tests/test_prompt_module_continuation.py::test_local_human_prompt_created_inside_module_attaches_active_continuation -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py::PromptServiceTests::test_public_request_alias_resolution_uses_index_before_scans -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py::PromptServiceTests::test_module_decision_command_does_not_derive_batch_id_from_request_id apps/server/tests/test_prompt_service.py::PromptServiceTests::test_module_decision_command_carries_prompt_instance_id_for_public_request_alias -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py::PromptServiceTests::test_mark_prompt_delivered_resolves_public_request_id_alias apps/server/tests/test_prompt_service.py::PromptServiceTests::test_external_decision_result_resolves_public_request_id_alias -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_batch_collector.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_stream_api.py -q`
- `npm --prefix apps/web test -- src/domain/stream/decisionProtocol.spec.ts src/headless/HeadlessGameClient.spec.ts src/hooks/useGameStream.spec.ts src/headless/frontendTransportAdapter.spec.ts`
- `npm --prefix apps/web test -- src/headless/httpDecisionPolicy.spec.ts src/headless/protocolReplay.spec.ts src/headless/HeadlessGameClient.spec.ts`
- `npm --prefix apps/web run build`
- `./.venv/bin/python -m pytest apps/server/tests/test_sessions_api.py::SessionsApiTests::test_external_ai_decision_callback_accepts_public_player_and_request_identity -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_sessions_api.py::SessionsApiTests::test_start_replay_session_start_includes_initial_active_faces -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_prompt_service_accepts_public_request_id_with_redis_prompt_store apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_prompt_service_expires_public_request_id_with_redis_prompt_store -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_prompt_service_uses_redis_alias_index_for_public_request_id_lookup -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_sequence.py apps/server/tests/test_redis_realtime_services.py -q -k "runtime_prompt_sequence_seed or prompt_sequence"`
- `./.venv/bin/python tools/plan_policy_gate.py`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `git diff --check`

## 2026-05-13 Prompt Identity Cleanup

- Removed `DecisionGateway`'s process-local request id fallback for prompt
  creation errors.
- Blocking human prompt replay now reuses an existing pending prompt with the
  same deterministic `request_id`; it does not create a new per-process/random
  request id and supersede the original prompt.
- AI decision events now use a deterministic protocol id derived from request
  type, player id, and public context fingerprint. At the time of this cleanup
  it did not replace the external AI worker/callback redesign; the HTTP
  external AI path was later moved to a pending prompt plus callback command
  boundary, while local/loopback AI remains a separate test-profile concern.
- Responsibility moved: request identity is no longer owned by a
  `DecisionGateway` in-memory counter. Prompt identity is owned by protocol
  boundary data, and duplicate pending prompts remain owned by the existing
  prompt lifecycle.
- Server `_LocalHumanDecisionClient` no longer reads or writes engine
  `HumanHttpPolicy._prompt_seq`. Runtime prompt sequence is seeded from
  checkpoint/domain logic and held by the server adapter while the engine
  transition is running.
- Responsibility intentionally remains: process-local runtime `_prompt_seq`
  ownership is still open and requires prompt boundary creation to move out of
  the policy adapter path. Engine standalone `HumanHttpPolicy._prompt_seq`
  remains for non-server human play.

Verification:

- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_decision_gateway_reuses_pending_prompt_id_when_blocking apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_decision_gateway_has_no_process_local_request_seq_fallback -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -q -k 'decision_gateway or runtime_prompt_boundary'`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_prompt_module_continuation.py::test_local_human_client_prompt_boundary_is_owned_by_builder apps/server/tests/test_prompt_module_continuation.py::test_local_human_prompt_created_inside_module_attaches_active_continuation -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_human_bridge_prompt_sequence_can_resume_from_checkpoint_value apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_module_resume_seeds_prompt_sequence_from_previous_same_module_decision -q`

## 2026-05-13 Runtime Matrix Coverage Sync

- Fixed `tests/test_module_runtime_playtest_matrix_doc.py` failures caused by
  stale coverage artifacts, not runtime rule changes.
- Added frontend prompt selector coverage for serial prompt request types already
  present in `round-combination.regression-pack.json`: `trick_to_use`,
  `specific_trick_reward`, `lap_reward`, `purchase_tile`, and
  `coin_placement`.
- Added `InitialRewardModule` to the RoundFrame module inventory in
  `docs/current/runtime/round-action-control-matrix.md`, matching
  `engine/runtime_modules/catalog.py`.
- Responsibility did not move: runtime contracts remain owned by the catalog and
  regression pack; the frontend spec and runtime matrix now track those
  contracts again.

Verification:

- `./.venv/bin/python -m pytest tests/test_module_runtime_playtest_matrix_doc.py -q`
- `npm --prefix apps/web test -- src/domain/selectors/promptSelectors.spec.ts`
- `python3 tools/plan_policy_gate.py`
- `git diff --check`

## 2026-05-13 Documentation Hygiene

- Renamed current documentation files under `docs/current` so filenames no
  longer contain shell-special square brackets.
- Preserved prefix semantics with plain names such as `PLAN_`, `ACTIVE_`, and
  `WORKLOG_`.
- Updated in-repo references, README pointers, tests, and
  `tools/plan_policy_gate.py`.
- Added policy that forbids square brackets in `docs/current` filenames and
  requires reference/policy gate updates in the same rename change.
- Added the mandatory pre-implementation contract to
  `docs/current/engineering/MANDATORY_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
  and root `AGENTS.md`.

Verification:

- bracket filename/reference check: `files=0`, `refs=0`
- `python3 tools/plan_policy_gate.py`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `git diff --check`

## 2026-05-13 Server Runtime Rebuild Phase 9 Current State

Phase 9 is reducing `RuntimeService` from command lifecycle owner to runtime
boundary adapter. The current split is:

- `SessionLoop` owns command lifecycle control flow through
  `SessionCommandExecutor`.
- `CommandRouter` only validates accepted command references and wakes
  `SessionLoopManager`.
- `CommandStreamWakeupWorker` observes Redis pending/resumable commands and
  wakes `SessionLoopManager`; it no longer directly calls runtime execution.
- `CommandRecoveryService` owns read-side command recovery queries.
- `CommandProcessingGuardService` owns consumer-offset checks, stale terminal
  classification, rejected/superseded/expired marking, and rejected offset
  advancement.
- `CommandExecutionGate` owns in-process active command/session gating and
  active runtime task deferral.
- `CommandBoundaryFinalizer` owns deferred commit finalization, latest
  `view_commit` emission, waiting prompt materialization, and finalization
  timing logs.
- `CommandBoundaryGameStateStore` owns command-boundary staging/deferred commit
  behavior and prevents internal module transitions from committing
  authoritatively mid-command.
- `CommandBoundaryRunner` owns command-boundary per-call store creation,
  transition repetition, terminal detection, finalizer call, module trace, and
  timing result assembly. `RuntimeService` only injects engine/persistence
  callables for that boundary.
- `runtime_prompt_sequence_seed()` lives in
  `apps/server/src/domain/prompt_sequence.py`, not `runtime_service.py`.
- Final command-boundary commit rechecks runtime lease ownership before
  authoritative Redis/view/prompt side effects.
- `RuntimeService.process_command_once()` has been removed. Production
  `SessionLoop` paths and diagnostic tests now use `SessionCommandExecutor`
  directly, while `RuntimeService` exposes only runtime-boundary lifecycle
  methods for command execution.
- `SessionLoop` no longer has a fallback to
  `RuntimeService.process_command_once()` when a runtime boundary lacks the
  lifecycle interface. Loop tests now exercise the lifecycle boundary path.

Important remaining responsibility:

- Prompt boundary construction is no longer owned by `_LocalHumanDecisionClient`;
  the remaining architectural question is whether the bridge-owned
  `PromptBoundaryBuilder` should later move up into `SessionCommandExecutor` or
  a UnitOfWork-style owner. Do not move it until command/prompt atomicity is
  being redesigned as one boundary.
- Keep `CommandBoundaryGameStateStore` as the explicit command atomicity staging
  boundary until a future UnitOfWork-style owner exists in `SessionLoop` or
  `SessionCommandExecutor`.
- Keep Redis authoritative and `view_commit` as read model; do not reintroduce
  route-level runtime execution or heartbeat-driven repair.

Representative verification already passed during this phase:

- focused service tests for command recovery, processing guard, execution gate,
  boundary finalizer, boundary store, session loop, router, stream, and wakeup
  worker
- full `apps/server/tests` passes through the Phase 9 checkpoints
- `npm --prefix apps/web test -- src/headless/protocolGateRunArtifacts.spec.ts src/headless/protocolGateRunProgress.spec.ts src/headless/protocolLatencyGate.spec.ts`
- `python3 tools/plan_policy_gate.py`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `git diff --check`

## 2026-05-12 Runtime Rebuild Evidence To Preserve

- The valid scaling baseline is `5 server instances + 1 Redis`, not
  `1 server + 5 Redis`. Current server state construction uses one global
  `MRN_REDIS_URL`, so multiple Redis containers behind one server are unused
  unless a session-aware routing layer is built.
- A 5-game isolated server/Redis run passed with per-game server and Redis.
- A 5-server/1-Redis run passed, isolating earlier concurrent failures away from
  Redis-only saturation.
- A single-server/20-game stress run failed on backend timing, not command loss:
  `InitialRewardModule` transition wall-clock dominated, with evidence showing
  engine transition time far above Redis commit and view commit time.
- Conclusion: the observed 20-game single-server bottleneck was server-side
  engine transition saturation under one Python server process, not Redis
  commit, view projection, missing ACK, duplicate view commit, or command inbox
  loss.

This evidence remains useful because it explains why server-instance count and
runtime ownership matter more than Redis fan-out for the current architecture.

## 2026-05-13 Phase 10 Prompt Replay Probe Fix

- Removed the nonblocking prompt replay wait from human prompt creation.
  `DecisionGateway.resolve_human_prompt(blocking_human_prompts=False)` now uses
  `PromptService.wait_for_decision(timeout_ms=0)` as an immediate resolved
  decision probe. That probe does not create a pending waiter and does not scan
  the full resolved hash for TTL pruning on every wait call.
- Pre-fix 5-server evidence showed `WeatherModule` prompt creation spending
  6773ms in `replay_wait_ms`, with Redis commit/view commit still bounded.
  Post-fix 5-server evidence completed all games with max transition 538ms and
  max command 1224ms.
- Restart, pending-prompt reconnect, and duplicate decision smokes passed.
  Duplicate decision replay returned `stale/already_resolved`.
- 20-game/1-server remains a capacity bottleneck by design of the test: after
  the prompt replay wait was removed, fail-fast showed command wall-clock
  5357ms under one server process while prompt timing count was 0 and
  Redis/view commit counts stayed at 1.

Responsibility result: prompt lifecycle replay probing no longer blocks prompt
materialization. The remaining 20-game/1-server failure belongs to single-server
runtime scheduling/capacity, not prompt identity, Redis commit, view projection,
ACK delivery, or command inbox dedupe.

## 2026-05-13 Protocol Gate Output Hygiene

- The direct full-stack protocol gate and repeated-game protocol gate runner now
  suppress compact progress output by default. Pass `--verbose-progress` only
  when live progress lines are useful enough to spend terminal/chat context.
- `--verbose-progress` is the explicit opt-in for investigation runs where
  progress lines are worth the terminal/chat context cost.
- In repeated runs, raw child stdout/stderr and progress remain persisted under
  each `game-N/raw/` directory, and failure diagnosis still starts from
  `PROTOCOL_GATE_FAILURE_POINTER` plus `summary/failure_reason.json`.

Responsibility result: long-run evidence ownership stays with file artifacts and
failure pointers. Chat/terminal output is no longer responsible for carrying
successful progress details.

## 2026-05-13 Session Loop Recovery Status Closure

- Closed stale Phase 2/3 checklist items in the active server-runtime rebuild
  plan against existing implementation evidence.
- The selected wake policy is lazy wake start: session start does not create a
  long-lived loop; accepted durable commands wake `SessionLoopManager` through
  `CommandRouter` or `CommandStreamWakeupWorker`.
- The loop is a bounded drain task, not an idle daemon. Lease ownership is scoped
  to each command execution and released in `SessionCommandExecutor.finally`;
  the manager task exits once the Redis inbox is idle.
- Restart recovery is covered by Redis command inbox plus worker polling, not
  by process-local queue state or a separate remote-owner pub/sub signal.

Responsibility result: no runtime responsibility moved in this checkpoint. The
plan now matches the already implemented ownership: Redis inbox is durable
authority, router/worker are wake paths, and `SessionLoopManager` owns one
process-local drain task per session. External AI command-boundary unification
remains open.

## 2026-05-13 HTTP External AI Command Boundary

- HTTP external AI transport no longer invokes the worker sender/healthchecker
  inside the session loop. It materializes a provider=`ai` pending prompt and
  stops at `PromptRequired`.
- Added an external AI decision callback route. Accepted callbacks go through
  `PromptService.submit_decision()` and `CommandInbox.accept_prompt_decision()`,
  then wake the session loop through `CommandRouter.wake_after_accept()`.
- Preserved provider=`ai` through pending prompt payload, submitted decision
  payload, persisted `decision_submitted` command, runtime decision resume, and
  stream ACK.
- Removed obsolete runtime-service tests that asserted the old forbidden
  behavior: direct in-loop HTTP worker calls, retry loops, and local AI fallback
  from the HTTP transport path. Worker API and helper validation remain covered
  outside the session-loop transport contract.

Responsibility result: HTTP external AI provider execution moved out of the
session loop. Decision acceptance remains in `PromptService`/`CommandInbox`.
Wake remains in `CommandRouter`. Redis command inbox remains the durable
authority. Local and loopback AI transports intentionally remain outside this
checkpoint.

## 2026-05-13 Simultaneous Batch Command Boundary

- `PromptService.submit_decision()` now routes simultaneous batch prompt
  responses through `BatchCollector` instead of appending one
  `decision_submitted` command per player.
- `PromptService.record_timeout_fallback_decision()` uses the same collector for
  simultaneous batch timeout fallback decisions, so human and timeout races are
  resolved by the collector's atomic completion primitive.
- Incomplete batch responses return accepted decision state with no command
  sequence. `PromptTimeoutWorker` now wakes the command router only when the
  accepted decision state contains a positive command sequence.
- `SessionLoop` accepts `batch_complete` as a runtime command, and
  `RuntimeService` reconstructs a `RuntimeDecisionResume` from the collected
  responses. Non-primary collected responses are applied to the active batch
  before the primary resume continues the engine transition.

Responsibility result: simultaneous batch completion ownership moved out of
route/timeout-side command append paths and into `BatchCollector`. The session
loop remains the only command execution path. `RuntimeService` still performs
the engine resume and state mutation, but it no longer decides whether a batch
is complete or creates per-response commands.

## 2026-05-13 One-Server Five-Game Baseline

- Live protocol gate with one server, one Redis, five concurrent games passed:
  `tmp/rl/full-stack-protocol/server-rebuild-live-5game-20260513-205642`.
- All five sessions completed with no stale ACK, rejected ACK, failed command,
  or raw-prompt fallback counts.
- Backend timing stayed inside the 5s gate: max command 1875ms and max
  transition 1232ms. Redis commit count and view commit count stayed at 1.
- Redis state inspector reported diagnostic `ok` for all five sessions.

Responsibility result: the current rebuild is not dependent on one server per
game for a five-game live smoke. The remaining one-server question is capacity
boundary measurement, not a known Redis/view-commit/prompt-lifecycle violation.

## 2026-05-13 One-Server Capacity Boundary

- Committed local reproducibility cleanup as `f1a24ead`
  (`chore: stabilize protocol gate local artifacts`): ignored `.playwright-mcp/`
  and passed `MRN_ADMIN_TOKEN` through the protocol compose file.
- One server plus one Redis with eight concurrent games passed:
  `tmp/rl/full-stack-protocol/server-rebuild-capacity-8game-1server-20260513-211035`.
  All eight sessions completed; max command was 3943ms, max transition was
  2159ms, Redis/view commit counts stayed at 1, and slow command/transition
  counts were 0.
- One server plus one Redis with ten concurrent games found the first measured
  SLO boundary:
  `tmp/rl/full-stack-protocol/server-rebuild-capacity-10game-1server-20260513-211951`.
  Game 3 failed `backend_timing` because command seq 1 took 5886ms for
  `reason=prompt_required`, above the 5000ms command SLO.
- The failure did not show a rule-flow or persistence contract break. For the
  failing command, `engine_loop_total_ms=203`, `redis_commit_count=1`,
  `view_commit_count=1`, and max transition stayed 1273ms. The excess was
  `executor_overhead_ms=5680`, which points to single-server runtime scheduling
  contention under concurrent command execution.

Responsibility result: no game-rule, Redis authority, `view_commit`, prompt
identity, ACK, or command-inbox responsibility moved or failed in this
checkpoint. The measured boundary is capacity/SLO ownership: a single server is
inside the current 5s command SLO at eight concurrent games and outside it at
ten concurrent games. Further 12/15-game one-server runs would characterize
overload, not find the first boundary, so they were not run.

## 2026-05-13 Protocol Evidence And Remote Gate Closure

- Committed and pushed fail-closed remote evidence gates as `fe882c7c`
  (`Harden external evidence gates`) on
  `codex/external-topology-protocol-ops`.
- Confirmed missing remote inputs are blocked by design: local Redis platform
  manifests fail with `--require-external-topology`, loopback worker URLs fail
  with `--require-non-local-endpoint`, and loopback game-server URLs fail with
  `--require-non-local-server`.
- Synchronized the runtime protocol plan status with actual evidence. Phase 0
  additive identity, Redis debug retention, baseline prompt lifecycle, and
  Redis viewer-outbox debug/indexing were implemented at that checkpoint.
  Later 2026-05-14 evidence in this journal and
  `PLAN_RUNTIME_PROTOCOL_STABILITY_AND_IDENTITY.md` supersedes the older
  residual list: opaque request IDs, first-class stale/resolved lifecycle
  states, and read-mode viewer outbox delivery are now implemented. The
  remaining protocol migration boundaries are numeric compatibility aliases,
  especially numeric `player_id` payload aliases and numeric
  `prompt_instance_id` lifecycle keys.
- Local validation passed: 190 server protocol/lifecycle/outbox tests, 76
  frontend headless/stream tests, smoke workflow gate, live protocol gate,
  bounded UI full-game progress, and full-stack live RL smoke at
  `tmp/rl/full-stack-protocol/codex-all-20260513`.

Responsibility result: no runtime ownership was silently moved in this
checkpoint. Evidence classification moved into scripts and status docs:
loopback/local runs are local evidence only, while remote/external evidence
requires non-local endpoint URLs, auth, and platform-filled Redis commands.
Protocol-plan responsibility also became explicit: completed additive/debug
foundations are separated from residual identity and outbox migration work.

## 2026-05-14 React Local Viewer Identity Bridge

- Added `LocalViewerIdentity` as the React-side local viewer model.
- Token-derived `session_pN_*` values and join-response `player_id` values are
  now normalized as legacy fallback inputs, not stored as the UI's whole viewer
  identity.
- `view_commit.viewer` public/protocol companions can now populate the same
  model, while existing display selectors still receive the resolved numeric
  `legacyPlayerId` bridge.
- Prompt actionability now consumes this model directly through
  `isPromptTargetedToIdentity()`, comparing public/protocol/viewer/seat identity
  before falling back to the legacy numeric bridge.
- Updated the protocol identity inventory and runtime protocol plan to record
  that this is an intermediate bridge, not numeric alias removal.

Responsibility result: token parsing and local viewer identity construction
moved out of `App.tsx` into the domain viewer helper. Prompt target comparison
moved into `promptSelectors`; `App.tsx` still owns feeding legacy numeric
selector inputs until the remaining render selectors can consume public/protocol
viewer identity directly.

## 2026-05-15 React Join Identity Companion Consumption

- Updated the frontend join-session API contract to include the public player,
  seat, viewer, legacy, and display identity fields already emitted by the
  server join response.
- `localViewerIdentityFromJoinResult()` now preserves those join-result
  companions in `LocalViewerIdentity` instead of reducing the result to numeric
  `player_id`.
- Numeric-only join responses still produce a legacy bridge identity for old
  sessions, and future string protocol `player_id` join responses can populate
  the viewer model without requiring a numeric bridge.

Responsibility result: join-result viewer identity construction now preserves
server-owned public/protocol identity at the React boundary. Numeric join
fields remain as legacy display/engine bridge inputs rather than the whole
local viewer identity.

## 2026-05-14 Frontend Prompt Instance Companion Preservation

- Added frontend/headless coverage that fails when `public_prompt_instance_id`
  is dropped after the server prompt boundary creates it.
- `promptViewModelFromActivePromptPayload()` now maps
  `public_prompt_instance_id` into the prompt continuation view model.
- `buildDecisionMessage()` serializes `public_prompt_instance_id` together
  with the numeric `prompt_instance_id`.
- Headless HTTP policy requests and compact decision trace payloads preserve
  the same public prompt-instance companion for external policy debugging and
  artifact inspection.

Responsibility result: no prompt lifecycle ownership moved. The numeric
`prompt_instance_id` remains the compatibility lifecycle bridge, and the web
decision boundary now owns preserving the already-created public companion
instead of silently dropping it before submit, policy input, or trace export.

## 2026-05-14 Actionable Prompt Without Legacy Seat Bridge

- Added selector coverage for public prompt identity that has `player_id`,
  `public_player_id`, `seat_id`, and `viewer_id` but no numeric
  `legacy_player_id`.
- `promptViewModelFromActivePromptPayload()` now builds an actionable prompt
  view model from that public/protocol identity instead of returning `null`
  until the numeric engine bridge is available.
- `PromptViewModel.playerId` is now nullable and means only the optional legacy
  display/engine bridge. The primary prompt target remains
  `PromptViewModel.identity.primaryPlayerId`.
- React decision serialization now uses public/protocol prompt identity first
  and includes `legacy_player_id` only when a numeric bridge is actually
  present.
- Prompt display strings kept their existing numeric `P2` output, while the
  later prompt-overlay migration made public/protocol identity visible instead
  of rendering `P?` solely because a numeric seat bridge is absent.

Responsibility result: actionable prompt construction moved off the numeric
legacy seat bridge. Numeric `PromptViewModel.playerId` intentionally remains as
display/headless compatibility data until those remaining consumers are migrated.

## 2026-05-14 Prompt Overlay Primary Identity Display

- Added selector coverage for `PromptViewModel.primaryPlayerId` and
  `primaryPlayerIdSource` on a public-only prompt with no numeric
  `legacy_player_id`.
- `PromptOverlay` now feeds header metadata from `prompt.primaryPlayerId`
  instead of the legacy top-level numeric `prompt.playerId` alias.
- Prompt i18n metadata helpers now accept `ProtocolPlayerId | null`, preserving
  existing `P2` numeric labels while allowing public/protocol string identity
  to be displayed when no legacy seat bridge exists.

Responsibility result: prompt header display ownership moved off
`PromptViewModel.playerId`. Numeric `playerId` remains only as the legacy
display/engine bridge for consumers that still need engine-seat numbers.

## 2026-05-14 Headless Prompt Routing Identity

- Added headless coverage for an active public prompt that has no numeric
  `legacy_player_id` bridge and for a mixed migration commit where the viewer
  exposes public identity while the active prompt remains legacy-only.
- `HeadlessGameClient` now routes active and raw prompts through
  `isPromptTargetedToIdentity()` using latest `view_commit.viewer`
  public/protocol/viewer/seat identity.
- The numeric `playerId` fallback remains narrowly scoped to prompts whose
  primary identity source is explicitly legacy, preserving transition-period
  compatibility without treating `PromptViewModel.playerId` as the primary
  target for public prompts.

Responsibility result: headless prompt target ownership moved from direct
`PromptViewModel.playerId === this.playerId` checks into the shared prompt
identity selector. Duplicate/retry ledgers and top-level trace seat keys
intentionally remain numeric compatibility surfaces.

## 2026-05-14 HTTP Decision Policy Primary Identity

- Added HTTP policy request coverage that fails when public primary player
  identity is already resolved on `HeadlessDecisionContext.identity` but prompt
  fields are stale or legacy-only.
- `buildHttpDecisionPolicyRequest()` now consumes
  `HeadlessDecisionContext.identity` directly instead of reinterpreting
  `PromptViewModel` fields in a second helper.
- `HttpDecisionPolicyRequest` now carries top-level `primary_player_id` and
  `primary_player_id_source` while preserving `legacy_player_id` compatibility.
- `HttpDecisionPolicyRequest.player_id` now uses public/protocol identity when
  available and carries `player_id_alias_role: "legacy_compatibility_alias"`
  only for legacy-only numeric fallback input.
- Numeric-only prompt requests still serialize `primary_player_id: 2` with
  `primary_player_id_source: "legacy"`, making the fallback explicit instead
  of pretending numeric `player_id` is the general primary identity.

Responsibility result: HTTP policy primary identity ownership moved from local
prompt reinterpretation to the already-resolved headless decision context.
External policy compatibility remains intact for legacy-only prompts because the
legacy numeric fallback is still labeled in the request.

## 2026-05-14 Headless Decision Primary Identity

- Added headless coverage for the mixed migration case where an active prompt
  still carries numeric top-level `player_id` as a legacy alias but also carries
  explicit public `primary_player_id`.
- `HeadlessGameClient` decision construction now passes
  `PromptViewModel.identity.primaryPlayerId` and `primaryPlayerIdSource` into
  `buildDecisionMessage()` instead of recomputing primary identity from the
  numeric alias.
- Numeric top-level `player_id` remains as the compatibility alias, but the
  decision now also carries `legacy_player_id` when the primary identity is not
  legacy so receivers do not have to infer the bridge from the alias. A later
  submitted-decision step moved the actual outbound top-level `player_id` off
  this numeric alias when the explicit primary identity is public/protocol.
- Decision trace top-level identity fields now use the prompt identity for
  decision events, while the generic trace default still uses the latest viewer
  identity for non-prompt events.

Responsibility result: headless decision primary identity ownership moved from
local fallback inference into the prompt selector's `PromptViewModel.identity`.
Numeric aliases remain only as compatibility fields until the protocol removal
gates close.

## 2026-05-14 Runtime Contract Numeric Alias Guard

- Added schema coverage that fails when outbound WebSocket decisions, inbound
  prompt payloads, or external-AI decision requests carry numeric `player_id`
  without primary identity metadata.
- Runtime contract schemas now keep numeric `player_id` compatible, but only
  when `player_id_alias_role`, `primary_player_id`, and
  `primary_player_id_source` are present.
- The local subset schema validator now handles the small `allOf` plus
  `if`/`then` subset needed by these frozen contract checks.

Responsibility result: detecting unlabeled numeric public identity moved into
the shared contract layer. Producers still own emitting the companion fields;
numeric alias removal remains a later compatibility-gated migration.

## 2026-05-14 Headless Trace Primary Identity

- Added headless trace coverage for both legacy-only and public-player decision
  traces.
- `HeadlessTraceEvent` now carries top-level `primary_player_id`,
  `primary_player_id_source`, protocol, legacy, public, seat, and viewer
  identity fields through the shared `recordTrace()` path.
- `view_commit_seen` trace events use the inbound commit viewer identity
  directly, so the first public commit trace is not limited by the previously
  cached client state.
- The duplicate suppression and retry ledgers were left unchanged because code
  inspection showed they are keyed by stream/request id, not by numeric
  `player_id`.

Responsibility result: trace identity interpretation moved off the numeric
`player_id` alias. The legacy numeric field remains in JSONL for compatibility
and display/debug grouping, but it is no longer the only top-level player
identity available to trace consumers.

## 2026-05-14 Protocol Harness Primary Identity Diagnostics

- Added harness coverage for public active-prompt identity in pace,
  command-latency, and repeated-prompt diagnostics.
- `ProtocolPaceDiagnostic` now exposes `activePromptPrimaryPlayerId` and source
  while keeping `activePromptPlayerId` as the legacy numeric alias.
- Repeated-prompt signatures and command-latency rows now prefer
  `active_prompt_primary_player_id` or trace `primary_player_id` before falling
  back to legacy numeric player ids.

Responsibility result: protocol-gate operator diagnostics no longer interpret
numeric active-prompt `player_id` as the primary identity. Seat numbers remain
available for display and legacy grouping only.

## 2026-05-14 Protocol Replay Primary Identity Export

- Added replay coverage for public primary player identity in rows,
  observations, and final player summaries.
- `ProtocolReplayRow` and `ProtocolReplayPlayerSummary` now expose
  `primary_player_id` plus `primary_player_id_source`.
- Numeric `player_id` remains available for reward/rank grouping and legacy
  display, but replay exports no longer present it as the only player identity.

Responsibility result: replay artifact identity moved to explicit primary
identity fields. Numeric player ids intentionally remain as display/training
grouping aliases because reward and rank calculations still consume engine-seat
snapshots.

## 2026-05-14 Debug Log Audit Primary Identity Grouping

- Added debug-log audit coverage for simultaneous public identities that share
  a request id, including cases where numeric `player_id` is absent and cases
  where nested `identity.primary_player_id` must beat a top-level numeric alias.
- `game_debug_log_audit.py` now groups duplicate frontend decisions, backend
  accepts, and draft-to-final prompt lifecycles with an identity key that
  prefers `primary_player_id`, public, protocol, viewer, and seat identity
  before falling back to numeric legacy/display fields.
- Existing numeric-only debug logs remain supported during the compatibility
  window.

Responsibility result: human diagnostic grouping moved off the bare numeric
`player_id` alias. Numeric values remain only as legacy/display fallback labels
for old logs.

## 2026-05-14 External AI Worker and Callback Public Player Identity

- Added regression coverage for `SessionService.resolve_protocol_player_id()`
  resolving a public string supplied as top-level `player_id`.
- The `/external-ai/decisions` callback request model now accepts string
  `player_id` and normalizes it through the same session identity adapter used
  by other protocol decision boundaries.
- The reference external AI worker `/decide` request model now accepts public or
  protocol string `player_id` plus explicit legacy/public/seat/viewer identity
  companions.
- `external_ai_full_stack_smoke.py` now sends public/protocol top-level
  `player_id` to both the worker `/decide` request and the server callback when
  the pending prompt provides that primary identity. Numeric `player_id` remains
  only for legacy-only prompt input and is labeled as a compatibility alias.

Responsibility result: public-string player resolution moved into
`SessionService.resolve_protocol_player_id()` for server callbacks, while the
worker boundary itself now accepts the same public/protocol identity contract
instead of forcing the smoke adapter to down-convert to a numeric alias.

## 2026-05-14 Redis Restart Smoke Public Decision Identity

- `redis_restart_smoke.py` now uses the prompt's explicit public/protocol
  primary identity as submitted decision `player_id` when available.
- The script still uses `legacy_player_id` as the replay prompt lookup bridge
  for operator-selected numeric player seats.
- Legacy-only prompts still submit numeric `player_id` and label it as
  `player_id_alias_role: "legacy_compatibility_alias"`.

Responsibility result: restart-smoke decision submission moved off the numeric
top-level alias when public/protocol identity exists. Numeric identity remains
only as replay lookup and legacy-only compatibility input.

## 2026-05-14 Headless Submitted Decision Public Identity

- Added decision-protocol and headless coverage that fails when an active prompt
  still carries numeric top-level `player_id` but also carries explicit public
  `primary_player_id`, and the outbound decision still submits the numeric
  alias.
- `buildDecisionMessage()` now chooses the submitted top-level `player_id` from
  explicit public/protocol `primaryPlayerId` before falling back to the legacy
  active-prompt `playerId`.
- Legacy-only decisions still submit numeric `player_id` and label it with
  `player_id_alias_role: "legacy_compatibility_alias"`.
- `HeadlessGameClient` keeps numeric trace `player_id` as the local seat/debug
  key, while the WebSocket decision payload itself now uses the public submitted
  identity in the mixed migration case.

Responsibility result: WebSocket decision submission moved from "forward the
active prompt top-level alias" to "submit explicit public/protocol primary
identity when available." Internal headless seat/debug identity and legacy-only
fallback routing intentionally remain numeric compatibility surfaces.

## 2026-05-14 React Submitted Decision Public Identity Coverage

- Added `useGameStream.spec.ts` coverage for the UI decision boundary where the
  active prompt still carries numeric top-level `playerId` but explicit
  `primaryPlayerId` is public.
- No production hook change was required: `useGameStream` already delegates
  decision payload serialization to `buildDecisionMessage()`, and that shared
  builder now owns submitted top-level `player_id` selection.
- The legacy numeric-only decision test remains in the same suite and continues
  to require `player_id_alias_role: "legacy_compatibility_alias"`.

Responsibility result: no new runtime responsibility moved. This locks the UI
submission boundary to the shared decision-protocol builder instead of adding a
parallel identity rule in the hook.

## 2026-05-14 External Topology Guard and Numeric Alias Companion Contract

- Redis platform smoke validation now rejects external-required manifests that
  retain local runtime preflight or local Docker Compose runtime commands, even
  if the manifest's `target_topology` is renamed to an external-looking value.
- Actual external Redis evidence remains open: it still requires a filled
  platform manifest with non-local restart and worker exec commands.
- WS decision, inbound prompt, inbound decision ACK, and external-AI request
  schemas now require `legacy_player_id` whenever top-level `player_id` remains
  numeric. Existing public string identity paths are unchanged.

Responsibility result: external-evidence classification moved from topology
name alone to manifest operation validation. Numeric player alias contracts now
make the legacy bridge explicit instead of requiring consumers to infer it from
the alias value. Numeric aliases intentionally remain during the compatibility
window.

## 2026-05-15 Local Viewer Identity Normalization Repair

- Added `localViewerIdentity.spec.ts` coverage for `view_commit.viewer` payloads
  that still carry numeric `player_id` while also carrying public player, seat,
  and viewer companions.
- `localViewerIdentityFromViewCommitViewer()` now treats numeric
  `viewer.player_id` as the legacy bridge when public companions are present,
  matching join-result normalization.
- `legacyPlayerId` remains available for existing display and engine-bridge
  selectors.

Responsibility result: local viewer identity construction now owns the
public-vs-legacy split consistently for both join results and authoritative
view commits. UI selectors, prompt submission, and server payload contracts did
not move.

## 2026-05-15 Headless Viewer Target Identity Repair

- Added `HeadlessGameClient.spec.ts` coverage for active prompts that expose a
  protocol string `player_id` while the authoritative viewer still carries a
  numeric `viewer.player_id` compatibility alias plus `public_player_id`.
- `promptTargetIdentity()` now normalizes the latest viewer identity the same
  way as local viewer state: public companions become the protocol target
  before numeric viewer aliases are considered.
- Legacy-only prompt routing still falls back to the numeric player bridge.

Responsibility result: headless prompt routing now owns viewer target
normalization before calling the shared prompt identity matcher. Server payloads,
HTTP policy serialization, and numeric engine bridges did not move.

## 2026-05-15 Prompt Service Primary Identity Repair

- Added `test_prompt_service.py` coverage for pending prompts that declare
  `primary_player_id_source: "public"` while carrying numeric
  `primary_player_id`.
- `PromptService.create_prompt()` now preserves only source/type-consistent
  explicit primary identity. Malformed public/protocol/legacy primary fields are
  repaired from public/protocol/legacy companions before pending prompt storage.
- Submitted decision command payloads inherit the repaired primary identity from
  the pending prompt.

Responsibility result: server prompt storage now owns primary identity
source/type validation before lifecycle records and command materialization.
View-state selectors and client/headless fallback repair remain compatibility
guards, not the first correction boundary.

## 2026-05-15 Prompt Selector Primary Identity Repair

- Added `promptSelectors.spec.ts` coverage for malformed active-prompt payloads
  that declare `primary_player_id_source: "public"` while sending numeric
  `primary_player_id`.
- `promptIdentityFromActivePromptPayload()` now accepts numeric explicit primary
  ids only for `legacy` source and string explicit primary ids only for
  `public` or `protocol` source.
- Valid public companions still repair malformed public/protocol primary fields;
  numeric `legacyPlayerId` remains the UI/engine bridge.

Responsibility result: prompt selector parsing now owns primary identity
source/type validation before prompt models reach UI or headless decision code.
Server materialization and numeric engine bridges did not move.

## 2026-05-15 Headless Trace Primary Identity Repair

- Added `HeadlessGameClient.spec.ts` coverage for compact view-commit traces
  receiving malformed `primary_player_id: 2` with
  `primary_player_id_source: "public"` plus a valid `public_player_id`
  companion.
- `compactActivePromptIdentity()` now accepts numeric explicit primary ids only
  when the declared source is `legacy`; public/protocol primary ids must be
  strings or fall back to public/protocol companions.
- Numeric `active_prompt_player_id` and `active_prompt_legacy_player_id` remain
  available as legacy/debug trace aliases.

Responsibility result: headless trace compaction now mirrors the decision
protocol primary-identity rule. It owns debug evidence normalization only; it
does not change server payloads, prompt selection, or engine numeric bridges.

## 2026-05-15 Protocol Replay Primary Identity Repair

- Added `protocolReplay.spec.ts` coverage for replay rows receiving malformed
  numeric `primary_player_id` with `primary_player_id_source: "public"` plus a
  valid `public_player_id` companion.
- `replayIdentityFieldsFromRecord()` now rejects numeric explicit primary ids
  when the declared source is `public` or `protocol`, and falls back to
  public/protocol companions before legacy display ids.
- Reward/rank grouping still uses numeric `player_id` as a legacy display
  alias.

Responsibility result: replay artifact generation now shares the same primary
identity validation rule as decision and trace boundaries. Runtime protocol
behavior and engine numeric bridges remain unchanged.

## 2026-05-15 Harness Diagnostic Primary Identity Repair

- Added `fullStackProtocolHarness.spec.ts` coverage for pace, repetition, and
  command-latency diagnostics receiving malformed numeric public primary ids in
  both active-prompt payloads and trace top-level identity fields.
- `activePromptTraceIdentity()` and `traceIdentity()` now reject numeric
  explicit primary ids when the declared source is `public` or `protocol`, then
  fall back to public/protocol companions before legacy display ids.
- Joined seat numbers and numeric `player_id` remain display/grouping aliases
  for harness clients.

Responsibility result: operator diagnostics now normalize primary identity the
same way as trace and replay artifacts. Harness grouping and runtime protocol
behavior remain unchanged.

## 2026-05-15 Prompt Service Decision Boundary Guard

- Added `PromptServiceTests` coverage for non-numeric submitted `player_id`
  values reaching `PromptService.submit_decision()` directly.
- Replaced the raw `int(payload["player_id"])` conversion with `_int_or_none()`
  and routed invalid or mismatched values through the existing
  `player_mismatch` lifecycle rejection path.
- External HTTP/WebSocket routes still own public/protocol identity resolution
  through `SessionService.resolve_protocol_player_id()`.

Responsibility result: `PromptService` now owns exception-free validation at the
numeric engine decision boundary. It does not become a public identity resolver;
that responsibility remains at the route/session adapter boundary.

## 2026-05-15 Frontend Transport Public Identity Evidence

- Added `frontendTransportAdapter.spec.ts` coverage for a public/protocol
  decision reaching the final WebSocket serialization boundary.
- The test verifies string top-level `player_id`, `primary_player_id`,
  `legacy_player_id`, public player/seat/viewer companions, and
  `public_prompt_instance_id` survive serialization without adding a numeric
  alias label.

Responsibility result: the frontend transport adapter remains a wire
serialization boundary. It preserves the decision protocol shape produced by
the shared builder; it does not interpret or repair identity.

## 2026-05-15 External AI Target Identity Conflict Guard

- Added external AI worker API coverage for conflicting target preference
  companions where public target identity points at one legal choice and the
  numeric legacy target alias points at another.
- Target preference resolution now evaluates public-player, seat, viewer, and
  numeric legacy companions as one candidate set, and ignores the preference
  when supplied companions resolve to different choices.
- Raw choice payload echo and numeric target bridge fields remain unchanged.

Responsibility result: external AI worker policy now owns conflict-safe target
preference interpretation. It does not validate the full request envelope or
remove numeric target aliases; those remain compatibility inputs until the
engine command boundary no longer needs them.

## 2026-05-15 WS Public Primary Contract Examples

- Added runtime-contract coverage requiring dedicated WebSocket examples for
  the preferred public-primary identity shape.
- Added `inbound.prompt.public_identity.json` and
  `outbound.decision.public_identity.json` with string top-level `player_id`,
  matching `primary_player_id`/`public_player_id`, and explicit
  `legacy_player_id`, `seat_id`, and `viewer_id` companions.
- Extended the same contract-example gate to `decision_ack` by adding
  `inbound.decision_ack.public_identity.json` and allowing public string
  payload `player_id` in the ACK schema.
- Existing numeric WebSocket examples remain as labeled compatibility-alias
  evidence.

Responsibility result: runtime-contract examples now document the preferred
public identity boundary without moving or deleting runtime compatibility
logic. Numeric alias interpretation remains in the current adapters and schemas.

## 2026-05-15 Visibility Projection Public Identity Bridge

- Added visibility projection coverage for public string top-level `player_id`
  on private `prompt` and `decision_ack` messages.
- `project_stream_message_for_viewer()` and active-prompt redaction now target
  private delivery by numeric `player_id` first, then explicit
  `legacy_player_id` when the protocol identity has already become public.
- Spectators and non-target seats still receive no private prompt or ACK
  payload.

Responsibility result: visibility projection can survive public-primary prompt
and ACK payloads without becoming a public identity resolver. It still uses the
numeric viewer bridge for authorization until viewer routing migrates to
public/seat/viewer identity.

## 2026-05-15 Decision ACK Public Primary Producer

- Updated `build_decision_ack_payload()` so ACKs with `public_player_id` emit a
  public string top-level `player_id`. This was later superseded by
  primary-only ACK publishing.
- The same ACK payload preserves the internal numeric seat as
  `legacy_player_id` and omits `player_id_alias_role`; numeric-only ACKs remain
  labeled legacy compatibility aliases.
- WebSocket human-decision ACKs and external-AI callback ACKs now verify the
  public-primary shape while keeping target delivery covered by the visibility
  projection bridge.

Responsibility result: ACK payload construction now owns preferred public wire
identity selection. It does not remove the numeric engine bridge or change
decision submission/routing authorization.

## 2026-05-15 Frontend Related-Player Display Companions

- Added selector coverage for turn-history event details whose related-player
  fields carry public/protocol `*_player_id` values plus prefixed legacy/public
  companions.
- Updated `streamSelectors` display summaries for rent, marker transfer,
  bankruptcy, game end, mark outcomes, and ability suppression to read prefixed
  legacy/seat companions before raw related-player aliases.
- Left turn-history participant relevance, board ownership state, and engine
  actor routing on the existing numeric bridge.

Responsibility result: human-facing event detail text now owns the related-player
display conversion at the selector boundary. Protocol identity, participant
indexing, and runtime storage remain unchanged.

## 2026-05-15 External AI Decision Requested Event Example

- Re-aligned the external-AI `decision_requested` event example with the
  runtime prompt publish contract: public/protocol identity is carried by
  `primary_player_id`, `public_player_id`, `seat_id`, and `viewer_id`; top-level
  `player_id` is intentionally absent.
- The numeric seat is preserved only as `legacy_player_id`.
- Left `inbound.event.schema.json` broad because domain events still share one
  compatibility envelope.

Responsibility result: runtime-contract examples now own primary-only public
event evidence for the runtime prompt/decision-requested publish boundary.
Event schema compatibility and engine routing bridges remain unchanged.

## 2026-05-15 Decision Sequence Event Identity Companions

- Tightened the frozen WebSocket decision sequence example test so any numeric
  direct `player_id` must carry explicit legacy/public/seat/viewer companions,
  and any numeric `acting_player_id` must carry the actor-prefixed companions.
- Updated `sequence.decision.accepted_then_domain.json` and
  `sequence.decision.timeout_then_domain.json` to show runtime fanout identity
  enrichment on decision requested/resolved/fallback events and actor domain
  events.
- Left `inbound.event.schema.json` broad because the shared event envelope still
  carries many domain event shapes during compatibility migration.

Responsibility result: sequence examples now document the runtime fanout
identity companion contract. Runtime fanout enrichment ownership and engine
numeric actor routing remain unchanged.

## 2026-05-15 View-State Event Actor Identity Companions

- Added the two with-view-state event examples to the frozen WebSocket event
  schema/example coverage.
- Added a focused example test requiring top-level `acting_player_id` events to
  carry actor-prefixed legacy/public/seat/viewer companions.
- Updated `inbound.event.turn_start.with_view_state.json` and
  `inbound.event.player_move.with_view_state.json` with those top-level actor
  companions while leaving nested `view_state` display ids unchanged.

Responsibility result: with-view-state event examples now document runtime
fanout actor identity enrichment at the event boundary. Nested view-state
selector/display migration remains intentionally out of scope.

## 2026-05-15 With-View-State Prompt Legacy Alias Metadata

- Added `inbound.prompt.trick_to_use.with_view_state.json` to frozen inbound
  prompt schema/example coverage.
- Added a focused example test requiring numeric prompt `player_id` fields to
  carry `player_id_alias_role`, `primary_player_id`,
  `primary_player_id_source`, and `legacy_player_id`.
- Updated the `trick_to_use` prompt example so both the top-level prompt payload
  and nested active prompt view label numeric `player_id` as a legacy
  compatibility alias.

Responsibility result: frozen prompt examples now own the rule that numeric
prompt target ids are never presented as unlabeled public identity. Runtime
prompt publishing, prompt routing, and selector/display migration remain
unchanged.

## 2026-05-15 Public Identity Visibility Projection

- Added visibility projection coverage for public-only private prompt,
  `decision_ack`, and private decision-event target routing without a numeric
  `legacy_player_id` bridge.
- Added embedded `view_state.prompt.active` coverage so an authorized viewer can
  keep a public-only active prompt while non-target/private data remains
  redacted through the existing projection path.
- Updated `visibility/projector.py` to match target viewers by
  `public_player_id`, `seat_id`, `viewer_id`, public/protocol
  `primary_player_id`, or public string top-level `player_id` before falling
  back to numeric `player_id` / `legacy_player_id`.

Responsibility result: private stream projection now owns public target matching
at the delivery/redaction boundary. Numeric viewer/player ids remain as
compatibility fallback and visibility-scope bridge; runtime payload creation,
auth, and engine routing remain unchanged.

## 2026-05-15 Frontend Stream Selector Local Identity

- Added selector coverage for a public-only local viewer identity matching
  derived player rows, marker ordering, and active-character slots without a
  numeric `legacyPlayerId`.
- Updated `streamSelectors` to accept a public/protocol/viewer/seat identity
  object for local-player matching on those surfaces while preserving numeric
  legacy ids as fallback.
- Updated `App.tsx` to pass the merged `LocalViewerIdentity` companion fields
  into those stream selector calls instead of reducing local highlighting to
  `effectivePlayerId`.
- Updated the match-table player card strip to consume selector-owned
  `isLocalPlayer` instead of recomputing local badges/classes by numeric
  `effectivePlayerId`.

Responsibility result: local-player highlighting for these stream selector
surfaces and match-table player cards moved off the numeric-only React bridge.
Board labels, turn history, prompt submission, and engine actor routing remain
unchanged.

## 2026-05-15 Frontend Turn-History Participant Companions

- Added selector coverage for turn-history events whose raw related-player
  fields and `participants` map carry public/protocol strings while explicit
  prefixed legacy/seat companions carry the display bridge.
- Updated `streamSelectors` participant extraction so rent and mark relevance
  uses `*_legacy_player_id` / `*_seat_index` companions before raw
  `*_player_id` aliases.
- Kept public/protocol ids opaque; they are not parsed or coerced into numeric
  display ids.

Responsibility result: turn-history participant highlighting and local
relevance moved off raw numeric related-player aliases. Board ownership labels,
engine actor routing, and persistence schemas remain unchanged.

## 2026-05-15 Frontend Board Display Companions

- Added selector coverage for ViewCommit board snapshots whose marker owner,
  tile owner, pawn list, and last-move player fields carry public/protocol
  string ids while explicit legacy companions carry the numeric display bridge.
- Updated `streamSelectors` board parsing to consume
  `marker_owner_legacy_player_id`, `owner_legacy_player_id`,
  `pawn_legacy_player_ids`, and last-move `legacy_player_id` before raw
  `*_player_id` aliases.
- Kept the adapter display-only: public/protocol strings are not parsed or
  coerced into numeric player ids.

Responsibility result: board marker, ownership, pawn, and last-move display
bridging is now owned by the stream-selector board adapter. Engine actor
routing, server fanout enrichment, and protocol alias removal remain unchanged.

## 2026-05-12 Runtime Rebuild Baseline

- The active rebuild plan is
  `docs/current/architecture/PLAN_SERVER_RUNTIME_REBUILD_2026-05-12.md`.
- Rejected directions included direct local queue command acceptance,
  pub/sub-only outbound delivery, non-atomic batch completion, weak deterministic
  prompt ids, and further expansion of `RuntimeService`.
- Accepted direction: Redis remains authoritative, accepted decisions become
  durable command references, `SessionLoop` drains commands, and external
  boundaries publish state through explicit commits and projected `view_commit`
  records.

## Journal Maintenance Rule

When adding to this file:

- Add only the current checkpoint and its responsibility result.
- Prefer one consolidated entry over one entry per micro-change.
- Remove old details once the active plan, tests, or status index carries the
  durable conclusion.
- Do not keep raw protocol logs here. Store bulky evidence under the run
  artifact directory and keep only decision-grade conclusions in this journal.

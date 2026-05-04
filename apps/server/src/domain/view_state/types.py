from __future__ import annotations

from typing import Literal, NotRequired, TypedDict


MarkerDraftDirection = Literal["clockwise", "counterclockwise"]
PlayerTurnOrderSource = Literal["marker_draft", "round_order", "player_id"]


class DerivedPlayerItemViewState(TypedDict):
    player_id: int
    display_name: str
    cash: int
    shards: int
    owned_tile_count: int
    trick_count: int
    hidden_trick_count: int
    public_tricks: list[str]
    hand_coins: int
    placed_coins: int
    total_score: int
    priority_slot: int | None
    current_character_face: str
    is_marker_owner: bool
    is_current_actor: bool
    turn_order_rank: int | None


class PlayerOrderingViewState(TypedDict):
    ordered_player_ids: list[int]
    turn_order_source: PlayerTurnOrderSource
    marker_owner_player_id: int | None
    marker_draft_direction: MarkerDraftDirection | None
    items: list[DerivedPlayerItemViewState]


PlayerCardRevealState = Literal["selected_private", "revealed"]


class PlayerCardAssignmentItemViewState(TypedDict):
    player_id: int
    priority_slot: int | None
    character: str
    reveal_state: PlayerCardRevealState
    is_current_actor: bool


class PlayerCardsViewState(TypedDict):
    items: list[PlayerCardAssignmentItemViewState]


class ActiveSlotItemViewState(TypedDict):
    slot: int
    player_id: int | None
    label: str | None
    character: str | None
    inactive_character: str | None
    is_current_actor: bool


class ActiveSlotsViewState(TypedDict):
    items: list[ActiveSlotItemViewState]


class MarkTargetCandidateViewState(TypedDict):
    slot: int
    player_id: int | None
    label: str | None
    character: str


class MarkTargetViewState(TypedDict):
    actor_slot: int | None
    candidates: list[MarkTargetCandidateViewState]


RevealTone = Literal["move", "effect", "economy"]


class RevealItemViewState(TypedDict):
    seq: int
    event_code: str
    event_order: int
    tone: RevealTone
    focus_tile_index: int | None
    is_interrupt: bool


class RevealsViewState(TypedDict):
    round_index: int | None
    turn_index: int | None
    items: list[RevealItemViewState]


class BoardLastMoveViewState(TypedDict):
    player_id: int | None
    from_tile_index: int | None
    to_tile_index: int | None
    path_tile_indices: list[int]


class BoardTileViewState(TypedDict):
    tile_index: int
    score_coin_count: int
    owner_player_id: int | None
    pawn_player_ids: list[int]


class BoardViewState(TypedDict, total=False):
    last_move: BoardLastMoveViewState | None
    tiles: list[BoardTileViewState]
    f_value: int | float | None
    marker_owner_player_id: int | None


class PromptChoiceItemViewState(TypedDict):
    choice_id: str
    title: str
    description: str
    value: dict[str, object] | None
    secondary: bool


class ActivePromptBehaviorViewState(TypedDict, total=False):
    normalized_request_type: str
    single_surface: bool
    auto_continue: bool
    chain_key: str
    chain_item_count: int
    current_item_deck_index: int | None


class PromptSurfaceLapRewardOptionViewState(TypedDict):
    choice_id: str
    cash_units: int
    shard_units: int
    coin_units: int
    spent_points: int


class PromptSurfaceMovementCardChoiceViewState(TypedDict):
    choice_id: str
    cards: list[int]
    title: str
    description: str


class PromptSurfaceMovementViewState(TypedDict):
    roll_choice_id: str | None
    card_pool: list[int]
    can_use_two_cards: bool
    card_choices: list[PromptSurfaceMovementCardChoiceViewState]


class PromptSurfaceLapRewardViewState(TypedDict):
    budget: int
    cash_pool: int
    shards_pool: int
    coins_pool: int
    cash_point_cost: int
    shards_point_cost: int
    coins_point_cost: int
    options: list[PromptSurfaceLapRewardOptionViewState]


class PromptSurfaceBurdenCardViewState(TypedDict):
    deck_index: int | None
    name: str
    description: str
    burden_cost: int | None
    is_current_target: bool


class PromptSurfaceBurdenExchangeViewState(TypedDict):
    burden_card_count: int
    current_f_value: int | None
    supply_threshold: int | None
    cards: list[PromptSurfaceBurdenCardViewState]


class PromptSurfaceMarkTargetCandidateViewState(TypedDict):
    choice_id: str
    target_character: str
    target_card_no: int | None
    target_player_id: int | None


class PromptSurfaceMarkTargetViewState(TypedDict):
    actor_name: str
    none_choice_id: str | None
    candidates: list[PromptSurfaceMarkTargetCandidateViewState]


class PromptSurfaceCharacterPickOptionViewState(TypedDict):
    choice_id: str
    name: str
    description: str


class PromptSurfaceCharacterPickViewState(TypedDict):
    phase: str
    draft_phase: int | None
    draft_phase_label: str | None
    choice_count: int
    options: list[PromptSurfaceCharacterPickOptionViewState]


class PromptSurfaceHandChoiceCardViewState(TypedDict):
    choice_id: str | None
    deck_index: int | None
    name: str
    description: str
    is_hidden: bool
    is_usable: bool


class PromptSurfaceHandChoiceViewState(TypedDict):
    mode: str
    pass_choice_id: str | None
    cards: list[PromptSurfaceHandChoiceCardViewState]


class PromptSurfacePurchaseTileViewState(TypedDict):
    tile_index: int | None
    cost: int | None
    yes_choice_id: str | None
    no_choice_id: str | None


class PromptSurfaceTileTargetOptionViewState(TypedDict):
    choice_id: str
    tile_index: int
    title: str
    description: str


class PromptSurfaceTrickTileTargetViewState(TypedDict):
    card_name: str
    target_scope: str
    candidate_tiles: list[int]
    options: list[PromptSurfaceTileTargetOptionViewState]


class PromptSurfaceCoinPlacementOptionViewState(TypedDict):
    choice_id: str
    tile_index: int
    title: str
    description: str


class PromptSurfaceCoinPlacementViewState(TypedDict):
    owned_tile_count: int
    options: list[PromptSurfaceCoinPlacementOptionViewState]


class PromptSurfaceDoctrineReliefOptionViewState(TypedDict):
    choice_id: str
    target_player_id: int | None
    burden_count: int | None
    title: str
    description: str


class PromptSurfaceDoctrineReliefViewState(TypedDict):
    candidate_count: int
    options: list[PromptSurfaceDoctrineReliefOptionViewState]


class PromptSurfaceGeoBonusOptionViewState(TypedDict):
    choice_id: str
    reward_kind: str
    title: str
    description: str


class PromptSurfaceGeoBonusViewState(TypedDict):
    actor_name: str
    options: list[PromptSurfaceGeoBonusOptionViewState]


class PromptSurfaceSpecificTrickRewardOptionViewState(TypedDict):
    choice_id: str
    deck_index: int | None
    name: str
    description: str


class PromptSurfaceSpecificTrickRewardViewState(TypedDict):
    reward_count: int
    options: list[PromptSurfaceSpecificTrickRewardOptionViewState]


class PromptSurfacePabalDiceModeOptionViewState(TypedDict):
    choice_id: str
    dice_mode: str
    title: str
    description: str


class PromptSurfacePabalDiceModeViewState(TypedDict):
    options: list[PromptSurfacePabalDiceModeOptionViewState]


class PromptSurfaceRunawayStepViewState(TypedDict):
    bonus_choice_id: str | None
    stay_choice_id: str | None
    one_short_pos: int | None
    bonus_target_pos: int | None
    bonus_target_kind: str


class PromptSurfaceActiveFlipOptionViewState(TypedDict):
    choice_id: str
    card_index: int | None
    current_name: str
    flipped_name: str


class PromptSurfaceActiveFlipViewState(TypedDict):
    finish_choice_id: str | None
    options: list[PromptSurfaceActiveFlipOptionViewState]


class PromptSurfaceViewState(TypedDict, total=False):
    kind: str
    blocks_public_events: bool
    movement: PromptSurfaceMovementViewState
    lap_reward: PromptSurfaceLapRewardViewState
    burden_exchange_batch: PromptSurfaceBurdenExchangeViewState
    mark_target: PromptSurfaceMarkTargetViewState
    character_pick: PromptSurfaceCharacterPickViewState
    hand_choice: PromptSurfaceHandChoiceViewState
    purchase_tile: PromptSurfacePurchaseTileViewState
    trick_tile_target: PromptSurfaceTrickTileTargetViewState
    coin_placement: PromptSurfaceCoinPlacementViewState
    doctrine_relief: PromptSurfaceDoctrineReliefViewState
    geo_bonus: PromptSurfaceGeoBonusViewState
    specific_trick_reward: PromptSurfaceSpecificTrickRewardViewState
    pabal_dice_mode: PromptSurfacePabalDiceModeViewState
    runaway_step: PromptSurfaceRunawayStepViewState
    active_flip: PromptSurfaceActiveFlipViewState


class PromptEffectContextViewState(TypedDict):
    label: str
    detail: str
    attribution: str
    tone: Literal["move", "effect", "economy"]
    source: str
    intent: str
    enhanced: bool
    source_player_id: NotRequired[int]
    source_family: NotRequired[str]
    source_name: NotRequired[str]
    resource_delta: NotRequired[dict[str, object]]


class ActivePromptViewState(TypedDict):
    request_id: str
    request_type: str
    player_id: int
    timeout_ms: int
    choices: list[PromptChoiceItemViewState]
    public_context: dict[str, object]
    behavior: ActivePromptBehaviorViewState
    surface: PromptSurfaceViewState
    effect_context: NotRequired[PromptEffectContextViewState]
    resume_token: NotRequired[str]
    frame_id: NotRequired[str]
    module_id: NotRequired[str]
    module_type: NotRequired[str]
    module_cursor: NotRequired[str]
    batch_id: NotRequired[str]


class PromptFeedbackViewState(TypedDict):
    request_id: str
    status: str
    reason: str


class PromptViewState(TypedDict, total=False):
    active: ActivePromptViewState
    last_feedback: PromptFeedbackViewState


class HandTrayCardViewState(TypedDict):
    key: str
    name: str
    description: str
    deck_index: int | None
    is_hidden: bool
    is_current_target: bool


class HandTrayViewState(TypedDict):
    cards: list[HandTrayCardViewState]


TurnBeatKind = Literal["move", "economy", "effect", "decision", "system"]


class TurnStageViewState(TypedDict):
    turn_start_seq: int | None
    actor_player_id: int | None
    round_index: int | None
    turn_index: int | None
    character: str
    weather_name: str
    weather_effect: str
    current_beat_kind: TurnBeatKind
    current_beat_event_code: str
    current_beat_request_type: str
    current_beat_seq: int | None
    focus_tile_index: int | None
    focus_tile_indices: list[int]
    prompt_request_type: str
    external_ai_worker_id: str
    external_ai_failure_code: str
    external_ai_fallback_mode: str
    external_ai_resolution_status: str
    external_ai_attempt_count: int | None
    external_ai_attempt_limit: int | None
    external_ai_ready_state: str
    external_ai_policy_mode: str
    external_ai_worker_adapter: str
    external_ai_policy_class: str
    external_ai_decision_style: str
    actor_cash: int | None
    actor_shards: int | None
    actor_hand_coins: int | None
    actor_placed_coins: int | None
    actor_total_score: int | None
    actor_owned_tile_count: int | None
    progress_codes: list[str]


TheaterTone = Literal["move", "economy", "system", "critical"]
TheaterLane = Literal["core", "prompt", "system"]


class SituationSceneViewState(TypedDict):
    actor_player_id: int | None
    round_index: int | None
    turn_index: int | None
    headline_seq: int | None
    headline_message_type: str
    headline_event_code: str
    weather_name: str
    weather_effect: str


class TheaterFeedItemViewState(TypedDict):
    seq: int
    message_type: str
    event_code: str
    tone: TheaterTone
    lane: TheaterLane
    actor_player_id: int | None
    round_index: int | None
    turn_index: int | None


class CoreActionFeedItemViewState(TypedDict):
    seq: int
    event_code: str
    actor_player_id: int | None
    round_index: int | None
    turn_index: int | None


AlertSeverity = Literal["warning", "critical"]


class TimelineItemViewState(TypedDict):
    seq: int
    message_type: str
    event_code: str


class CriticalAlertItemViewState(TypedDict):
    seq: int
    message_type: str
    event_code: str
    severity: AlertSeverity


class SceneViewState(TypedDict):
    situation: SituationSceneViewState
    theater_feed: list[TheaterFeedItemViewState]
    core_action_feed: list[CoreActionFeedItemViewState]
    timeline: list[TimelineItemViewState]
    critical_alerts: list[CriticalAlertItemViewState]


class RuntimeProjectionViewState(TypedDict, total=False):
    runner_kind: str
    latest_module_path: list[str]
    round_stage: str
    turn_stage: str
    active_sequence: str
    active_prompt_request_id: str
    active_frame_id: str
    active_frame_type: str
    active_module_id: str
    active_module_type: str
    active_module_status: str
    active_module_cursor: str
    active_module_idempotency_key: str
    draft_active: bool
    trick_sequence_active: bool
    card_flip_legal: bool


class ViewStatePayload(TypedDict, total=False):
    players: PlayerOrderingViewState
    player_cards: PlayerCardsViewState
    active_slots: ActiveSlotsViewState
    mark_target: MarkTargetViewState
    reveals: RevealsViewState
    board: BoardViewState
    prompt: PromptViewState
    hand_tray: HandTrayViewState
    turn_stage: TurnStageViewState
    scene: SceneViewState
    runtime: RuntimeProjectionViewState

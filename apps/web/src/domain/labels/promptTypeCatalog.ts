export const KNOWN_PROMPT_TYPES = [
  "movement",
  "runaway_step_choice",
  "lap_reward",
  "draft_card",
  "final_character",
  "trick_to_use",
  "purchase_tile",
  "hidden_trick_card",
  "mark_target",
  "coin_placement",
  "geo_bonus",
  "doctrine_relief",
  "active_flip",
  "specific_trick_reward",
  "burden_exchange",
] as const;

const PROMPT_TYPE_LABELS: Record<string, string> = {
  movement: "Move Decision",
  runaway_step_choice: "Runaway Move Choice",
  lap_reward: "Lap Reward Choice",
  draft_card: "Draft Selection",
  final_character: "Final Character Choice",
  final_character_choice: "Final Character Choice",
  trick_to_use: "Trick Usage",
  purchase_tile: "Tile Purchase",
  hidden_trick_card: "Hidden Trick Choice",
  mark_target: "Mark Target",
  coin_placement: "Token Placement",
  geo_bonus: "Geo Bonus Choice",
  doctrine_relief: "Doctrine Relief Choice",
  active_flip: "Active Card Flip",
  specific_trick_reward: "Specific Trick Reward",
  burden_exchange: "Burden Exchange",
};

export function promptLabelForType(requestType: string): string {
  if (!requestType.trim()) {
    return "Prompt";
  }
  return PROMPT_TYPE_LABELS[requestType] ?? requestType;
}

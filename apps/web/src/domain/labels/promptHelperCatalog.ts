export const DEFAULT_PROMPT_HELPER_TEXT = "Choose one option for the current prompt.";

const PROMPT_HELPERS: Record<string, string> = {
  movement:
    "Choose how to move this turn. You can roll dice, use move cards, or combine one card and one die if allowed.",
  runaway_step_choice: "Choose whether to apply the runaway +1 step effect.",
  lap_reward: "Choose the resource type for lap reward.",
  draft_card: "Choose one character from the current draft candidates.",
  final_character: "Choose the final character for this round.",
  final_character_choice: "Choose the final character for this round.",
  trick_to_use: "Choose a trick card to use now, or skip.",
  purchase_tile: "Choose whether to purchase the landed tile.",
  hidden_trick_card: "Choose one hidden trick card for this round.",
  mark_target: "Choose a target for the mark effect.",
  coin_placement: "Choose where to place your score token.",
  geo_bonus: "Choose one geo bonus option.",
  doctrine_relief: "Choose a doctrine relief target.",
  active_flip: "Flip one card, or select finish if you are done flipping.",
  specific_trick_reward: "Choose a trick card reward.",
  burden_exchange: "Choose whether to exchange burden cards.",
};

export function promptHelperForType(requestType: string): string {
  return PROMPT_HELPERS[requestType] ?? DEFAULT_PROMPT_HELPER_TEXT;
}

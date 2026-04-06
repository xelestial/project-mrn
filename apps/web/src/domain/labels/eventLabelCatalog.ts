import type { LocaleMessages } from "../../i18n/types";
import { DEFAULT_EVENT_LABEL_TEXT } from "../../i18n/defaultText";

type EventLabelText = LocaleMessages["eventLabel"];

export function eventLabelForCode(eventCode: string, eventLabelText: EventLabelText = DEFAULT_EVENT_LABEL_TEXT): string {
  if (!eventCode.trim()) {
    return eventLabelText.genericEvent;
  }
  return eventLabelText.events[eventCode as keyof typeof eventLabelText.events] ?? eventCode;
}

export function nonEventLabelForMessageType(
  messageType: string,
  eventLabelText: EventLabelText = DEFAULT_EVENT_LABEL_TEXT
): string {
  if (!messageType.trim()) {
    return eventLabelText.genericMessage;
  }
  return eventLabelText.nonEvents[messageType as keyof typeof eventLabelText.nonEvents] ?? eventLabelText.genericMessage;
}

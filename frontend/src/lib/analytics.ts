export type AnalyticsEvent =
  | "search_submitted"
  | "filter_applied"
  | "filter_cleared"
  | "sort_changed"
  | "property_opened"
  | "whatsapp_clicked"
  | "phone_clicked"
  | "email_clicked"
  | "original_listing_clicked"
  | "map_opened"
  | "share_clicked"
  | "load_error"
  | "empty_results";

export function track(event: AnalyticsEvent, properties: Record<string, string | number | boolean> = {}) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("eretz:analytics", { detail: { event, properties } }));
}


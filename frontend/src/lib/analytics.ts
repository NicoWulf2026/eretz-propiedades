export type AnalyticsEvent =
  | "search_submitted"
  | "natural_language_search"
  | "filter_applied"
  | "filter_removed"
  | "filter_cleared"
  | "sort_changed"
  | "zero_results"
  | "map_moved"
  | "search_this_area"
  | "draw_zone"
  | "property_opened"
  | "favorite_added"
  | "compare_added"
  | "property_hidden"
  | "contact_started"
  | "contact_channel_selected"
  | "whatsapp_clicked"
  | "phone_clicked"
  | "email_clicked"
  | "original_listing_clicked"
  | "real_estate_opened"
  | "claim_started"
  | "map_opened"
  | "share_clicked"
  | "load_error"
  | "empty_results";

export function track(event: AnalyticsEvent, properties: Record<string, string | number | boolean> = {}) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("eretz:analytics", { detail: { event, properties } }));
}


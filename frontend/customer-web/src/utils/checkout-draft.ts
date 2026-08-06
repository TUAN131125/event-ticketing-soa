import type { CustomerContactDraft } from '@event-ticketing/shared-ui/frontend-esb-contract';

export type CheckoutDraft = {
  eventId: string;
  eventName?: string;
  seatIds: string[];
  contact?: CustomerContactDraft;
  updatedAt: string;
};

const STORAGE_KEY = 'evently.checkoutDraft';

type StoredCheckoutSelection = Pick<CheckoutDraft, 'eventId' | 'eventName' | 'seatIds' | 'updatedAt'>;

/**
 * Restores only non-PII checkout selection state. Customer name, email and phone are carried in
 * router memory for the active journey and are deliberately never written to browser storage.
 */
export function readCheckoutDraft(): CheckoutDraft | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<StoredCheckoutSelection>;
    if (!value.eventId || !Array.isArray(value.seatIds) || value.seatIds.length === 0) return null;
    return {
      eventId: value.eventId,
      eventName: value.eventName,
      seatIds: value.seatIds.filter((seat): seat is string => typeof seat === 'string'),
      updatedAt: value.updatedAt ?? new Date().toISOString(),
    };
  } catch {
    return null;
  }
}

/** Returns the complete in-memory draft while persisting only event/seat selection. */
export function writeCheckoutDraft(draft: Omit<CheckoutDraft, 'updatedAt'>): CheckoutDraft {
  const value: CheckoutDraft = { ...draft, updatedAt: new Date().toISOString() };
  const stored: StoredCheckoutSelection = {
    eventId: value.eventId,
    eventName: value.eventName,
    seatIds: value.seatIds,
    updatedAt: value.updatedAt,
  };
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
  } catch {
    // Selection persistence is optional. Router state still carries the active journey.
  }
  return value;
}

export function clearCheckoutDraft(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing to clear in restricted storage modes.
  }
}

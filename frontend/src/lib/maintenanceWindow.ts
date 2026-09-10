/**
 * Scheduled maintenance: 10 Sep 2026, 1:00 PM – 3:30 PM IST (UTC+5:30).
 * Soft cutover window for ledger migrations (DCA / EasyA / Hedge Fund).
 */

/** 2026-09-10 13:00:00 IST = 07:30 UTC */
export const MAINTENANCE_START_UTC_MS = Date.UTC(2026, 8, 10, 7, 30, 0, 0);

/** 2026-09-10 15:30:00 IST = 10:00 UTC */
export const MAINTENANCE_END_UTC_MS = Date.UTC(2026, 8, 10, 10, 0, 0, 0);

export const MAINTENANCE_LABEL_IST = "1:00–3:30 PM IST · 10 Sep 2026";

export function isMaintenanceWindow(now: Date | number = Date.now()): boolean {
  if (process.env.NEXT_PUBLIC_MAINTENANCE_FORCE === "1") {
    return true;
  }
  const t = typeof now === "number" ? now : now.getTime();
  return t >= MAINTENANCE_START_UTC_MS && t < MAINTENANCE_END_UTC_MS;
}

export function maintenanceEndsAt(): Date {
  return new Date(MAINTENANCE_END_UTC_MS);
}

export function msUntilMaintenanceEnd(now: Date | number = Date.now()): number {
  const t = typeof now === "number" ? now : now.getTime();
  return Math.max(0, MAINTENANCE_END_UTC_MS - t);
}

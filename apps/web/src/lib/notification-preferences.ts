import { createClient } from "@/lib/supabase/client";

/**
 * Real read/write of `notification_preferences`. RLS restricts every row to
 * its owner (`auth.uid() = user_id`), so these run safely from the browser
 * with the anon key -- there is no path to another user's preferences.
 *
 * The row itself is created by the `handle_new_profile` trigger at signup,
 * so this only ever reads and updates; it never inserts.
 */

export interface NotificationPreferences {
  aplusplusEnabled: boolean;
  aplusEnabled: boolean;
  bgradeEnabled: boolean;
  xauusdEnabled: boolean;
  eurusdEnabled: boolean;
  gbpusdEnabled: boolean;
  btcusdEnabled: boolean;
  ethusdEnabled: boolean;
  browserEnabled: boolean;
  telegramEnabled: boolean;
  telegramChatId: string | null;
  emailEnabled: boolean;
}

export const DEFAULT_PREFERENCES: NotificationPreferences = {
  aplusplusEnabled: true,
  aplusEnabled: true,
  bgradeEnabled: false,
  xauusdEnabled: true,
  eurusdEnabled: true,
  gbpusdEnabled: true,
  btcusdEnabled: true,
  ethusdEnabled: true,
  browserEnabled: false,
  telegramEnabled: false,
  telegramChatId: null,
  emailEnabled: false,
};

interface PreferencesRow {
  aplusplus_enabled: boolean;
  aplus_enabled: boolean;
  bgrade_enabled: boolean | null;
  xauusd_enabled: boolean;
  eurusd_enabled: boolean;
  gbpusd_enabled: boolean;
  btcusd_enabled: boolean | null;
  ethusd_enabled: boolean | null;
  browser_enabled: boolean;
  telegram_enabled: boolean;
  telegram_chat_id: string | null;
  email_enabled: boolean;
}

const SELECT =
  "aplusplus_enabled, aplus_enabled, bgrade_enabled, xauusd_enabled, eurusd_enabled, gbpusd_enabled, " +
  "btcusd_enabled, ethusd_enabled, browser_enabled, telegram_enabled, telegram_chat_id, email_enabled";

function fromRow(row: PreferencesRow): NotificationPreferences {
  return {
    aplusplusEnabled: row.aplusplus_enabled,
    aplusEnabled: row.aplus_enabled,
    bgradeEnabled: row.bgrade_enabled ?? false,
    xauusdEnabled: row.xauusd_enabled,
    eurusdEnabled: row.eurusd_enabled,
    gbpusdEnabled: row.gbpusd_enabled,
    // Nullable in the type because the columns arrive in a later migration
    // (20260830000012). If it hasn't been run yet, fall back to the default
    // rather than rendering the toggle as off, which would be wrong.
    btcusdEnabled: row.btcusd_enabled ?? true,
    ethusdEnabled: row.ethusd_enabled ?? true,
    browserEnabled: row.browser_enabled,
    telegramEnabled: row.telegram_enabled,
    telegramChatId: row.telegram_chat_id,
    emailEnabled: row.email_enabled,
  };
}

export type LoadResult =
  | { ok: true; preferences: NotificationPreferences }
  | { ok: false; error: string };

export async function loadPreferences(): Promise<LoadResult> {
  try {
    const supabase = createClient();
    const { data: userData } = await supabase.auth.getUser();
    const user = userData?.user;
    if (!user) return { ok: false, error: "You need to be signed in to load your notification settings." };

    const { data, error } = await supabase
      .from("notification_preferences")
      .select(SELECT)
      .eq("user_id", user.id)
      .maybeSingle();

    if (error) return { ok: false, error: error.message };
    if (!data) {
      return {
        ok: false,
        error: "No notification preferences row exists for your account yet.",
      };
    }
    return { ok: true, preferences: fromRow(data as unknown as PreferencesRow) };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Could not load your settings." };
  }
}

export type SaveResult = { ok: true } | { ok: false; error: string };

export async function savePreferences(preferences: NotificationPreferences): Promise<SaveResult> {
  try {
    const supabase = createClient();
    const { data: userData } = await supabase.auth.getUser();
    const user = userData?.user;
    if (!user) return { ok: false, error: "You need to be signed in to save your notification settings." };

    const { error } = await supabase
      .from("notification_preferences")
      .update({
        aplusplus_enabled: preferences.aplusplusEnabled,
        aplus_enabled: preferences.aplusEnabled,
        bgrade_enabled: preferences.bgradeEnabled,
        xauusd_enabled: preferences.xauusdEnabled,
        eurusd_enabled: preferences.eurusdEnabled,
        gbpusd_enabled: preferences.gbpusdEnabled,
        btcusd_enabled: preferences.btcusdEnabled,
        ethusd_enabled: preferences.ethusdEnabled,
        browser_enabled: preferences.browserEnabled,
        telegram_enabled: preferences.telegramEnabled,
        telegram_chat_id: preferences.telegramChatId,
        email_enabled: preferences.emailEnabled,
      })
      .eq("user_id", user.id);

    if (error) return { ok: false, error: error.message };
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Could not save your settings." };
  }
}

import type { Metadata } from "next";
import { Suspense } from "react";

import { DatabaseChoice } from "@/components/shared/layout/database-switch";
import { SettingsSection, SettingsSections } from "@/components/shared/layout/settings-section";
import { ThemeChoice } from "@/components/shared/layout/theme-toggle";
import { Skeleton } from "@/components/ui/skeleton";
import { getDatabase } from "@/lib/api/server";

export const metadata: Metadata = { title: "Settings" };

/** The console's own settings, kept in this browser; product data lives under Country config. */
export default function SettingsPage() {
  return (
    <SettingsSections>
      <SettingsSection title="Appearance">
        <ThemeChoice />
      </SettingsSection>
      <SettingsSection title="Database">
        <Suspense fallback={<Skeleton className="h-40" />}>
          <CurrentDatabaseChoice />
        </Suspense>
      </SettingsSection>
    </SettingsSections>
  );
}

async function CurrentDatabaseChoice() {
  const database = await getDatabase();
  // Keyed so the banner's "Back to live" resets the choice it shows.
  return <DatabaseChoice key={database} database={database} />;
}

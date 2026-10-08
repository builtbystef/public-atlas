import type { Metadata } from "next";
import { Suspense } from "react";

import { DatabaseChoice } from "@/components/shared/layout/database-switch";
import { PageHeader } from "@/components/shared/layout/page-header";
import { SettingsSection, SettingsSections } from "@/components/shared/layout/settings-section";
import { ThemeChoice } from "@/components/shared/layout/theme-toggle";
import { Skeleton } from "@/components/ui/skeleton";
import { getDatabase } from "@/lib/api/server";

export const metadata: Metadata = { title: "Settings" };

/** The console's own settings, kept in this browser; product data lives under Countries. */
export default function SettingsPage() {
  return (
    <>
      <PageHeader
        title="Settings"
        description="How this browser's console looks and which database it reads."
      />
      <SettingsSections>
        <SettingsSection
          title="Appearance"
          description="Light or dark surfaces. The choice is kept in this browser only."
        >
          <ThemeChoice />
        </SettingsSection>
        <SettingsSection
          title="Database"
          description="Which database every page reads. The choice is kept in this browser only."
        >
          <Suspense fallback={<Skeleton className="h-40" />}>
            <CurrentDatabaseChoice />
          </Suspense>
        </SettingsSection>
      </SettingsSections>
    </>
  );
}

async function CurrentDatabaseChoice() {
  const database = await getDatabase();
  // Keyed so the banner's "Back to live" resets the choice it shows.
  return <DatabaseChoice key={database} database={database} />;
}

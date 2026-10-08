"use client";

import { MonitorIcon, MoonIcon, SunIcon } from "lucide-react";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

import { RadioCards } from "@/components/shared/radio-cards";

const themes = ["system", "light", "dark"] as const;

type Theme = (typeof themes)[number];

const themeLabels: Record<Theme, string> = {
  system: "System theme",
  light: "Light theme",
  dark: "Dark theme",
};

const themeDescriptions: Record<Theme, string> = {
  system: "Follows the operating system's setting.",
  light: "Light surfaces, whatever the system says.",
  dark: "Dark surfaces, whatever the system says.",
};

const themeIcons: Record<Theme, typeof SunIcon> = {
  system: MonitorIcon,
  light: SunIcon,
  dark: MoonIcon,
};

function isTheme(value: string | undefined): value is Theme {
  return value !== undefined && (themes as readonly string[]).includes(value);
}

/**
 * The theme is read from the browser, so the server does not know it; until
 * the component has mounted it renders the system option so the markup
 * matches on both sides.
 */
function useChosenTheme(): { theme: Theme; setTheme: (theme: Theme) => void } {
  const mounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
  const { theme, setTheme } = useTheme();
  return { theme: mounted && isTheme(theme) ? theme : "system", setTheme };
}

/** The theme, one card per option, on the settings page. */
export function ThemeChoice() {
  const { theme, setTheme } = useChosenTheme();
  return (
    <RadioCards
      name="theme"
      legend="Theme"
      value={theme}
      onChange={setTheme}
      options={themes.map((value) => {
        const Icon = themeIcons[value];
        return {
          value,
          label: themeLabels[value],
          description: themeDescriptions[value],
          icon: <Icon />,
        };
      })}
    />
  );
}

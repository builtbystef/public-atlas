import type { ComponentType, SVGProps } from "react";

/**
 * The sidebar's own icons. They are drawn on lucide's 24-unit grid with round
 * strokes, so they sit beside the rest of the console's icons, and each fills
 * one part of itself with a tint of `currentColor` that the nav deepens on the
 * current page through `--nav-icon-tint`.
 */
export type NavIcon = ComponentType<SVGProps<SVGSVGElement>>;

function Icon({ children, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

/** The tinted part of an icon: a filled shape under the strokes. */
function Tint({ d }: { d: string }) {
  return (
    <path
      d={d}
      fill="currentColor"
      stroke="none"
      style={{ opacity: "var(--nav-icon-tint, 0.25)" }}
    />
  );
}

/** Saved lists: a bookmarked list of rows. */
export function SavedListsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <path d="M3.5 6h8M3.5 12h8M3.5 18h13" />
      <Tint d="M15 3.5h5.5v9l-2.75-2-2.75 2z" />
      <path d="M15 3.5h5.5v9l-2.75-2-2.75 2z" />
    </Icon>
  );
}

/** Institutions: a public building's portico. */
export function InstitutionsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <Tint d="M3.5 9.5 12 4l8.5 5.5z" />
      <path d="M3.5 9.5 12 4l8.5 5.5z" />
      <path d="M6 12.5v4.5M10 12.5v4.5M14 12.5v4.5M18 12.5v4.5" />
      <path d="M4.5 17h15M3 20.5h18" />
    </Icon>
  );
}

/** Places: a pin on the map. */
export function PlacesIcon(props: SVGProps<SVGSVGElement>) {
  const pin = "M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z";
  return (
    <Icon {...props}>
      <Tint d={pin} />
      <path d={pin} />
      <circle cx="12" cy="10" r="2.25" />
    </Icon>
  );
}

/** Country config: a flag on its pole. */
export function CountriesIcon(props: SVGProps<SVGSVGElement>) {
  const flag = "M5 4.5c2.3-1.4 4.7-1.4 7 0s4.7 1.4 7 0v9c-2.3 1.4-4.7 1.4-7 0s-4.7-1.4-7 0z";
  return (
    <Icon {...props}>
      <Tint d={flag} />
      <path d={flag} />
      <path d="M5 21V3" />
    </Icon>
  );
}

/** Runs: something set going that comes round again. */
export function RunsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <path d="M20.5 12a8.5 8.5 0 1 1-2.5-6" />
      <path d="M18.5 2.5V6H15" />
      <Tint d="M10 8.75v6.5L15.25 12z" />
      <path d="M10 8.75v6.5L15.25 12z" />
    </Icon>
  );
}

/** Assignments: a clipboard of tasks being ticked off. */
export function AssignmentsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <path d="M8.5 4.5H7a2 2 0 0 0-2 2V19a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V6.5a2 2 0 0 0-2-2h-1.5" />
      <Tint d="M9.5 2.5h5a1 1 0 0 1 1 1V6a1 1 0 0 1-1 1h-5a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1z" />
      <rect x="8.5" y="2.5" width="7" height="4.5" rx="1" />
      <path d="m8.5 12.5 1.25 1.25 2.25-2.25M14 12.5h2M8.5 17.5h7.5" />
    </Icon>
  );
}

/** Review queue: the rubber stamp that approves what the agent found. */
export function ReviewIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="5.5" r="2.5" />
      <path d="M10.75 8v3.5M13.25 8v3.5" />
      <Tint d="M6 11.5h12a1.5 1.5 0 0 1 1.5 1.5v2.5H4.5V13A1.5 1.5 0 0 1 6 11.5z" />
      <path d="M6 11.5h12a1.5 1.5 0 0 1 1.5 1.5v2.5h-15V13A1.5 1.5 0 0 1 6 11.5z" />
      <path d="M5.5 20h13" />
    </Icon>
  );
}

/** Evals: the scales the agent's work is weighed on. */
export function EvalsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <path d="M12 4v16.5M8 20.5h8M4.5 7h15" />
      <circle cx="12" cy="4" r="0.5" fill="currentColor" />
      <path d="M4.5 7 2.25 13M4.5 7l2.25 6M19.5 7l-2.25 6M19.5 7l2.25 6" />
      <Tint d="M2 13h5a2.5 2.5 0 0 1-5 0zM17 13h5a2.5 2.5 0 0 1-5 0z" />
      <path d="M2 13h5a2.5 2.5 0 0 1-5 0zM17 13h5a2.5 2.5 0 0 1-5 0z" />
    </Icon>
  );
}

/** Settings: two sliders. */
export function SettingsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <Icon {...props}>
      <path d="M4 7.5h8.5M17.5 7.5H20M4 16.5h2.5M11.5 16.5H20" />
      <Tint d="M17.5 7.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0zM11.5 16.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0z" />
      <circle cx="15" cy="7.5" r="2.5" />
      <circle cx="9" cy="16.5" r="2.5" />
    </Icon>
  );
}

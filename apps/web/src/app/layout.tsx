import type { Metadata } from "next";
import { Geist } from "next/font/google";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import "./globals.css";

import { Providers } from "./providers";

// Exposes --font-sans on <html>; globals.css maps it to Tailwind's font-sans.
const geist = Geist({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: { default: "Public Atlas", template: "%s · Public Atlas" },
  description: "A verified map of the public sector and its procurement signal sources.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // next-themes sets the `dark` class on <html> before hydration.
    <html lang="en" className={cn("font-sans", geist.variable)} suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

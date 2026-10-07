import { ImageResponse } from "next/og";

import { Logo } from "@/components/shared/logo";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

/** The same tile as icon.svg, as the PNG that iOS home screens and Safari pinned tabs want. */
export default function AppleIcon() {
  return new ImageResponse(
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#18181b",
        borderRadius: 40,
      }}
    >
      <Logo width={124} height={124} fill="#fafafa" />
    </div>,
    size,
  );
}

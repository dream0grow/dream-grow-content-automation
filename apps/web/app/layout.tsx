import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Providers } from "@/components/providers";

export const metadata: Metadata = {
  title: "Dream Grow Content Studio",
  description: "AI-assisted multi-channel content production",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

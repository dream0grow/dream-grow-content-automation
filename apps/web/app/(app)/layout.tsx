import type { ReactNode } from "react";

import { Sidebar } from "@/components/sidebar";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 px-6 py-6 max-w-7xl">{children}</main>
    </div>
  );
}

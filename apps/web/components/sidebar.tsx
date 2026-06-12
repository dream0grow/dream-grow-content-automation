"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Calendar, FileText, Gauge, GitBranch, LayoutDashboard,
  Plug, Sparkles,
} from "lucide-react";

import { cn } from "@/lib/utils";

const ITEMS = [
  { href: "/dashboard", label: "대시보드", icon: LayoutDashboard },
  { href: "/contents",  label: "콘텐츠", icon: FileText },
  { href: "/calendar",  label: "캘린더", icon: Calendar },
  { href: "/analytics", label: "분석",   icon: Gauge },
  { href: "/learning",  label: "학습",   icon: GitBranch },
  { href: "/brand",     label: "브랜드", icon: Sparkles },
  { href: "/integrations", label: "연동", icon: Plug },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden md:flex flex-col w-56 shrink-0 border-r border-border bg-white h-screen sticky top-0">
      <div className="p-4 border-b border-border">
        <div className="font-semibold text-lg">Dream Grow</div>
        <div className="text-xs text-muted-foreground">Content Studio</div>
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {ITEMS.map((it) => {
          const active = pathname?.startsWith(it.href);
          const Icon = it.icon;
          return (
            <Link
              key={it.href}
              href={it.href}
              className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors",
                active ? "bg-primary text-primary-foreground" : "hover:bg-muted"
              )}
            >
              <Icon className="h-4 w-4" />
              {it.label}
            </Link>
          );
        })}
      </nav>
      <div className="p-3 border-t border-border">
        <Link href="/contents/new" className="btn-accent w-full justify-center">
          새 콘텐츠
        </Link>
      </div>
    </aside>
  );
}

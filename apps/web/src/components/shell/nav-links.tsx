"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const links = [
  { href: "/marketplace", label: "Marketplace" },
  { href: "/library", label: "Library" },
  { href: "/traces", label: "My Traces" },
  { href: "/upload", label: "Upload" },
  { href: "/settings", label: "Settings" },
];

export function NavLinks() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1">
      {links.map(({ href, label }) => (
        <Link
          key={href}
          href={href}
          className={cn(
            "rounded-md px-3 py-1.5 text-sm transition-colors",
            pathname === href || pathname.startsWith(`${href}/`)
              ? "font-medium text-foreground"
              : "text-muted-foreground hover:bg-accent hover:text-foreground",
          )}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}

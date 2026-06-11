import Link from "next/link";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/traces", label: "Traces" },
  { href: "/uploads", label: "Uploads" },
] as const;

/** /traces and /uploads are one workspace surface behind a single nav item
 *  (4_pages.md): parsed traces on one tab, the ingest dropzone + file
 *  history on the other. Tabs are links, so URLs and deep links hold. */
export function WorkspaceTabs({ active }: { active: "/traces" | "/uploads" }) {
  return (
    <nav className="flex gap-4 border-b">
      {TABS.map(({ href, label }) => (
        <Link
          key={href}
          href={href}
          className={cn(
            "-mb-px border-b-2 px-1 pb-2 text-sm transition-colors",
            href === active
              ? "border-primary font-medium text-foreground"
              : "border-transparent text-muted-foreground hover:border-border hover:text-foreground",
          )}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}

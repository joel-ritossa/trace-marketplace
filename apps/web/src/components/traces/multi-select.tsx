"use client";

import { ChevronDown } from "lucide-react";
import { humanize } from "@/components/review/taxonomy";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

export type MultiSelectGroup = { label?: string; values: string[] };

/** Multi-select over a closed vocabulary: a trigger summarizing the picks
 *  over a checkbox menu that stays open while picking. Shared by the filter
 *  panel (task category / failure mode) and the turn relabel form. */
export function MultiSelect({
  groups,
  value,
  onChange,
  placeholder,
  className,
  "aria-label": ariaLabel,
}: {
  groups: MultiSelectGroup[];
  value: string[];
  onChange: (value: string[]) => void;
  placeholder: string;
  className?: string;
  "aria-label"?: string;
}) {
  const known = new Set(groups.flatMap((g) => g.values));
  // Active values the menu can't author (a stored subscription, a hand-edited
  // URL) still render and can be unticked.
  const extra = value.filter((v) => !known.has(v));
  const all = extra.length > 0 ? [...groups, { label: "Other values", values: extra }] : groups;

  function toggle(item: string, checked: boolean) {
    onChange(checked ? [...value, item] : value.filter((v) => v !== item));
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={ariaLabel}
          className={cn(
            "flex h-8 w-full items-center justify-between gap-1 rounded-md border bg-background px-2 text-left text-xs text-foreground",
            value.length === 0 && "text-muted-foreground",
            className,
          )}
        >
          <span className="truncate">
            {value.length === 0 ? placeholder : value.map(humanize).join(", ")}
          </span>
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-80 min-w-56">
        {all.map((group, i) => (
          <div key={group.label ?? i}>
            {group.label && (
              <DropdownMenuLabel className="text-xs text-muted-foreground">
                {group.label}
              </DropdownMenuLabel>
            )}
            {group.values.map((item) => (
              <DropdownMenuCheckboxItem
                key={item}
                checked={value.includes(item)}
                onCheckedChange={(checked) => toggle(item, checked === true)}
                onSelect={(e) => e.preventDefault()}
                className="text-xs"
              >
                {humanize(item)}
              </DropdownMenuCheckboxItem>
            ))}
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** The product mark (DESIGN.md §App Shell): a span-waterfall motif drawn in
 *  currentColor so it inherits both schemes. The one sanctioned non-lucide SVG. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={className} fill="currentColor">
      <rect x="3" y="4.5" width="12" height="3" rx="1.5" />
      <rect x="7" y="10.5" width="14" height="3" rx="1.5" />
      <rect x="11" y="16.5" width="8" height="3" rx="1.5" />
    </svg>
  );
}

import { ScrollText } from "lucide-react";

export default function HomePage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Traces</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Traces you upload will appear here.
      </p>
      <div className="mt-8 flex flex-col items-center rounded-lg border bg-background px-6 py-16 text-center">
        <ScrollText className="size-8 text-muted-foreground" strokeWidth={1.5} />
        <p className="mt-4 text-sm font-medium">No traces yet</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Trace upload arrives with the next slice.
        </p>
      </div>
    </div>
  );
}

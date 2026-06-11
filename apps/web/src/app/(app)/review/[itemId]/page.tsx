import { ResolveView } from "@/components/review/resolve-view";

export default async function ReviewItemPage({
  params,
}: {
  params: Promise<{ itemId: string }>;
}) {
  const { itemId } = await params;
  // Full content width by design (4_pages.md): evidence + form get the room.
  // Keyed so "Resolve & next" gets a fresh form for the next item.
  return <ResolveView key={itemId} itemId={itemId} />;
}

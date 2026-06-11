import { useCallback, useEffect, useState } from "react";
import { formatDate } from "../lib/format";
import { useRealtimeRefetch } from "../lib/realtime";
import { listReviewItems, type ReviewItem } from "../lib/review";
import { ReviewItemPage } from "./ReviewItemPage";

const REVIEW_POLL_MS = 60_000;

export function ReviewTab({
  webUrl,
  onOpenCount,
}: {
  webUrl: string;
  onOpenCount: (count: number) => void;
}) {
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openItemId, setOpenItemId] = useState<string | null>(null);

  const reload = useCallback(() => {
    listReviewItems({ status: "open", limit: 100 })
      .then((res) => {
        setItems(res.items);
        setError(null);
        onOpenCount(res.total);
      })
      .catch(() => setError("Could not load the review queue. Check the API is running."));
  }, [onOpenCount]);

  // Realtime invalidation with a fallback poll, like the notification center.
  useEffect(() => {
    reload();
    const timer = setInterval(reload, REVIEW_POLL_MS);
    return () => clearInterval(timer);
  }, [reload]);
  useRealtimeRefetch("review_items", reload);

  if (openItemId !== null) {
    // Keyed so "Resolve & next" gets a fresh form for the next item.
    return (
      <ReviewItemPage
        key={openItemId}
        itemId={openItemId}
        webUrl={webUrl}
        onBack={() => setOpenItemId(null)}
        onOpenItem={setOpenItemId}
        onResolved={reload}
      />
    );
  }

  return (
    <div className="page">
      <div>
        <h1>Review</h1>
        <p className="hint" style={{ marginTop: 2 }}>
          Low-confidence verdicts on your traces, newest first. Your answers land with human
          provenance and confidence 1.00.
        </p>
      </div>

      {error ? (
        <p className="error-text">{error}</p>
      ) : items === null ? (
        <p className="hint">Loading…</p>
      ) : items.length === 0 ? (
        <section className="card">
          <p className="hint">Queue’s clear — nothing needs your judgment right now.</p>
        </section>
      ) : (
        items.map((item) => (
          <section key={item.review_item_id} className="card">
            <div className="row spread">
              <div style={{ minWidth: 0 }}>
                <span style={{ fontWeight: 600 }}>{item.trace.name}</span>
                <p className="hint" style={{ marginTop: 2 }}>
                  From upload {item.upload_filename} · {formatDate(item.created_at)}
                </p>
              </div>
              <button
                className="btn outline small"
                onClick={() => setOpenItemId(item.review_item_id)}
              >
                Resolve…
              </button>
            </div>
          </section>
        ))
      )}
    </div>
  );
}

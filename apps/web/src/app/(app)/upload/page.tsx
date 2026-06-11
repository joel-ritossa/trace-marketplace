import { redirect } from "next/navigation";

/** Merged into /uploads (4_pages.md): the route survives only for old links. */
export default function UploadPage() {
  redirect("/uploads");
}

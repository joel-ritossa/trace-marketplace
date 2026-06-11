import { UploadFlow } from "@/components/uploads/upload-flow";

export default function UploadPage() {
  return (
    <div>
      <h1 className="text-2xl font-semibold tracking-tight">Upload</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Contribute an agent trace. Files are validated, preserved raw, and ingested in the
        background.
      </p>
      <div className="mt-8">
        <UploadFlow />
      </div>
    </div>
  );
}

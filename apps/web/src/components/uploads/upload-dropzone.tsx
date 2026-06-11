"use client";

import { useRef, useState } from "react";
import { FileJson, UploadCloud } from "lucide-react";
import { Button } from "@/components/ui/button";
import { UPLOAD_MAX_MB } from "@/lib/api/uploads";
import { cn } from "@/lib/utils";

export function UploadDropzone({
  disabled,
  onFile,
}: {
  disabled: boolean;
  onFile: (file: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleFiles(files: FileList | null) {
    const file = files?.[0];
    if (file) onFile(file);
  }

  return (
    <div
      className={cn(
        "flex flex-col items-center rounded-lg border border-dashed bg-background px-6 py-12 text-center transition-colors",
        dragging && "border-ring bg-secondary",
        disabled && "pointer-events-none opacity-60",
      )}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        handleFiles(e.dataTransfer.files);
      }}
    >
      {dragging ? (
        <FileJson className="size-8 text-muted-foreground" strokeWidth={1.5} />
      ) : (
        <UploadCloud className="size-8 text-muted-foreground" strokeWidth={1.5} />
      )}
      <p className="mt-4 text-sm font-medium">Drop a trace file here</p>
      <p className="mt-1 text-sm text-muted-foreground">
        One OTLP JSON file, up to {UPLOAD_MAX_MB} MB.
      </p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-4"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      >
        Choose file
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept="application/json,.json"
        className="hidden"
        onChange={(e) => {
          handleFiles(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}

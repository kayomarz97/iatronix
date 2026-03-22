"use client";

import { useState, useEffect, useCallback } from "react";
import { API_KEY_STORAGE_KEY } from "@/lib/constants";
import type { DocumentInfo, DocumentListResponse } from "@/lib/types";

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [verifiedCount, setVerifiedCount] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const getApiKey = () => localStorage.getItem(API_KEY_STORAGE_KEY) || "";

  const fetchDocuments = useCallback(async () => {
    const apiKey = getApiKey();
    if (!apiKey) return;

    try {
      const res = await fetch("/api/documents", {
        headers: { "X-API-Key": apiKey },
      });
      if (res.ok) {
        const data: DocumentListResponse = await res.json();
        setDocuments(data.documents);
        setVerifiedCount(data.verified_count);
      }
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const uploadFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setMessage("Only PDF files are accepted");
      return;
    }

    setUploading(true);
    setMessage(null);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/documents/upload", {
        method: "POST",
        headers: { "X-API-Key": getApiKey() },
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        setMessage(data.detail || "Upload failed");
      } else {
        setMessage(
          data.verified
            ? `Uploaded & verified (${data.publisher || "known publisher"})`
            : "Uploaded (unverified — only visible to you)"
        );
        fetchDocuments();
      }
    } catch {
      setMessage("Network error");
    } finally {
      setUploading(false);
    }
  };

  const deleteDoc = async (id: number) => {
    try {
      const res = await fetch(`/api/documents/${id}`, {
        method: "DELETE",
        headers: { "X-API-Key": getApiKey() },
      });
      if (res.ok) {
        fetchDocuments();
      }
    } catch {
      // ignore
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadFile(file);
  };

  return (
    <div className="max-w-2xl mx-auto pt-8 space-y-8">
      <div>
        <h1 className="text-3xl font-bold">Documents</h1>
        <p className="text-sm text-text-secondary mt-1">
          Upload medical PDFs. Verified documents from known publishers are
          searchable by all users.
        </p>
      </div>

      {/* Upload zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          dragActive
            ? "border-primary bg-primary/5"
            : "border-border hover:border-primary/50"
        }`}
      >
        <p className="text-sm text-text-secondary mb-3">
          {uploading
            ? "Processing PDF..."
            : "Drag & drop a PDF here, or click to browse"}
        </p>
        <label className="inline-block px-4 py-2 bg-primary text-white rounded-md text-sm cursor-pointer min-h-[44px] leading-[28px]">
          Choose File
          <input
            type="file"
            accept=".pdf"
            onChange={handleFileInput}
            className="hidden"
            disabled={uploading}
          />
        </label>
        <p className="text-xs text-text-muted mt-2">Max 20MB</p>
      </div>

      {message && (
        <div className="p-3 rounded-lg bg-surface-alt border border-border text-sm">
          {message}
        </div>
      )}

      {/* Stats */}
      <div className="flex gap-4 text-sm">
        <div className="p-3 rounded-md bg-surface-alt border border-border flex-1 text-center">
          <div className="text-2xl font-bold">{documents.length}</div>
          <div className="text-text-muted">Your uploads</div>
        </div>
        <div className="p-3 rounded-md bg-surface-alt border border-border flex-1 text-center">
          <div className="text-2xl font-bold">{verifiedCount}</div>
          <div className="text-text-muted">Verified in library</div>
        </div>
      </div>

      {/* Document list */}
      {documents.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-lg font-semibold">Your Uploads</h2>
          {documents.map((doc) => (
            <div
              key={doc.id}
              className="p-3 rounded-md border border-border flex items-center justify-between"
            >
              <div>
                <div className="font-medium text-sm">{doc.title}</div>
                <div className="text-xs text-text-muted flex gap-2 mt-1">
                  {doc.file_name && <span>{doc.file_name}</span>}
                  {doc.page_count && <span>{doc.page_count} pages</span>}
                  {doc.verified ? (
                    <span className="text-green-500">
                      Verified{doc.publisher ? ` — ${doc.publisher}` : ""}
                    </span>
                  ) : (
                    <span className="text-yellow-500">Unverified</span>
                  )}
                </div>
              </div>
              <button
                onClick={() => deleteDoc(doc.id)}
                className="text-xs text-danger hover:underline"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

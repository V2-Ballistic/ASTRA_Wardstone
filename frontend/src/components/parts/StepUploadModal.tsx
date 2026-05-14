'use client';
import { useCallback, useRef, useState } from 'react';
import { partsLibraryAPI } from '@/lib/parts-api';
import { formatApiError } from '@/lib/errors';

interface StepUploadModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (pendingImportId: number) => void;
  onDuplicateExistingPart?: (partId: number, wpn: string) => void;
}

const MAX_FILE_SIZE_MB = 50;
const ACCEPTED_EXTENSIONS = ['.step', '.stp'];

export function StepUploadModal({
  open, onClose, onSuccess, onDuplicateExistingPart,
}: StepUploadModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateFile = (f: File): string | null => {
    const ext = '.' + (f.name.split('.').pop() || '').toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      return `Invalid file type "${ext}". Only .step and .stp accepted.`;
    }
    if (f.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      return `File size ${(f.size / 1024 / 1024).toFixed(1)} MB exceeds ${MAX_FILE_SIZE_MB} MB limit.`;
    }
    if (f.size === 0) return 'File is empty.';
    return null;
  };

  // Phase 0 (sysarch-prep §0.3) — wrap in useCallback so the eslint
  // react-hooks/exhaustive-deps rule is satisfied when handleDrop (also
  // useCallback) lists it as a dependency. The body only references
  // state setters, which are stable identities — empty dep array is OK.
  const handleFileSelect = useCallback((f: File) => {
    const err = validateFile(f);
    if (err) {
      setError(err);
      return;
    }
    setFile(f);
    setError(null);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFileSelect(dropped);
  }, [handleFileSelect]);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const res = await partsLibraryAPI.uploadStep(file, setProgress);
      const data = res.data;
      if (data.duplicate) {
        if (data.pending_import_id) {
          onSuccess(data.pending_import_id);
        } else if (data.existing_part_id && onDuplicateExistingPart) {
          onDuplicateExistingPart(data.existing_part_id, data.existing_wpn || '');
        } else {
          setError('This file is already in the library.');
        }
      } else if (data.pending_import_id) {
        onSuccess(data.pending_import_id);
      }
    } catch (err: unknown) {
      setError(formatApiError(err, 'Upload failed.'));
    } finally {
      setUploading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setProgress(0);
    setError(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-lg mx-4 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Upload STEP File
          </h2>
          <button
            onClick={onClose}
            disabled={uploading}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 disabled:opacity-50"
          >
            ✕
          </button>
        </div>

        {!file && (
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={
              `border-2 border-dashed rounded-lg p-8 text-center cursor-pointer ` +
              `transition-colors duration-150 ` +
              (dragOver
                ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                : 'border-gray-300 dark:border-gray-600 hover:border-blue-400')
            }
          >
            <div className="text-4xl mb-2">📦</div>
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Drop a STEP file here or click to browse
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              .step or .stp — max {MAX_FILE_SIZE_MB} MB
            </p>
            <input
              ref={inputRef}
              type="file"
              accept=".step,.stp"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFileSelect(f);
              }}
            />
          </div>
        )}

        {file && (
          <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <div className="text-2xl">📄</div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                {file.name}
              </p>
              <p className="text-xs text-gray-500">
                {(file.size / 1024).toFixed(1)} KB
              </p>
            </div>
            {!uploading && (
              <button
                onClick={handleReset}
                className="text-xs text-blue-600 hover:underline"
              >
                Remove
              </button>
            )}
          </div>
        )}

        {uploading && (
          <div className="mt-3">
            <div className="h-2 bg-gray-200 dark:bg-gray-700 rounded">
              <div
                className="h-full bg-blue-500 rounded transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-xs text-gray-500 mt-1">{progress}% uploaded</p>
          </div>
        )}

        {error && (
          <div className="mt-3 p-2 bg-red-50 dark:bg-red-900/20 rounded border border-red-200 dark:border-red-800">
            <p className="text-sm text-red-800 dark:text-red-200">{error}</p>
          </div>
        )}

        <div className="mt-4 flex gap-2 justify-end">
          <button
            onClick={onClose}
            disabled={uploading}
            className="px-3 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-600 disabled:opacity-50 hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Cancel
          </button>
          <button
            onClick={handleUpload}
            disabled={!file || uploading}
            className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded disabled:opacity-50 hover:bg-blue-700"
          >
            {uploading ? 'Uploading...' : 'Upload'}
          </button>
        </div>
      </div>
    </div>
  );
}

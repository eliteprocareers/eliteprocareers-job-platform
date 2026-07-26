import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { api } from '../lib/api';
import type { CVUpload, CVUploadTriggerResponse, CoverLetterStyleSample } from '../lib/types';

const POLL_INTERVAL_MS = 3000;
const POLL_DURATION_MS = 5 * 60 * 1000;

const SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.txt'];
const MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024;

export default function Profile() {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [selectError, setSelectError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const uploadMutation = useMutation({
    mutationFn: async (selected: File) => {
      const formData = new FormData();
      formData.append('file', selected);
      const { data } = await api.post<CVUploadTriggerResponse>('/profile/cv-upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return data;
    },
    onSuccess: (res) => {
      setUploadId(res.upload_id);
      setIsPolling(true);
    },
  });

  const statusQuery = useQuery({
    queryKey: ['cv-upload-status', uploadId],
    queryFn: async () => {
      const { data } = await api.get<CVUpload>(`/profile/cv-upload-status/${uploadId}`);
      return data;
    },
    enabled: !!uploadId,
    refetchInterval: (query) => {
      if (!isPolling) return false;
      const currentStatus = query.state.data?.status;
      if (currentStatus === 'completed' || currentStatus === 'failed') return false;
      return POLL_INTERVAL_MS;
    },
  });

  useEffect(() => {
    if (!isPolling) return;
    const timeout = setTimeout(() => setIsPolling(false), POLL_DURATION_MS);
    return () => clearTimeout(timeout);
  }, [isPolling]);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    setSelectError(null);
    if (!selected) {
      setFile(null);
      return;
    }
    const lowerName = selected.name.toLowerCase();
    const hasValidExtension = SUPPORTED_EXTENSIONS.some((ext) => lowerName.endsWith(ext));
    if (!hasValidExtension) {
      setSelectError(`Unsupported file type. Supported: ${SUPPORTED_EXTENSIONS.join(', ')}.`);
      setFile(null);
      return;
    }
    if (selected.size === 0) {
      setSelectError('Selected file is empty.');
      setFile(null);
      return;
    }
    if (selected.size > MAX_UPLOAD_SIZE_BYTES) {
      setSelectError(`File exceeds the ${MAX_UPLOAD_SIZE_BYTES / (1024 * 1024)}MB limit.`);
      setFile(null);
      return;
    }
    setFile(selected);
  }

  function handleUpload() {
    if (!file) return;
    setUploadId(null);
    uploadMutation.mutate(file);
  }

  function handleUploadAnother() {
    setFile(null);
    setUploadId(null);
    setIsPolling(false);
    uploadMutation.reset();
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  const status = statusQuery.data?.status;

  // --- Cover letter style sample (tone/style reference only -- never a
  // real cover letter, never shown to an employer) ---
  const sampleFileInputRef = useRef<HTMLInputElement>(null);

  const sampleQuery = useQuery({
    queryKey: ['cover-letter-sample'],
    queryFn: async () => {
      try {
        const { data } = await api.get<CoverLetterStyleSample>('/profile/cover-letter-sample');
        return data;
      } catch (err) {
        if (axios.isAxiosError(err) && err.response?.status === 404) return null;
        throw err;
      }
    },
  });

  const sampleUploadMutation = useMutation({
    mutationFn: async (selected: File) => {
      const formData = new FormData();
      formData.append('file', selected);
      const { data } = await api.post<CoverLetterStyleSample>(
        '/profile/cover-letter-sample',
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cover-letter-sample'] });
      if (sampleFileInputRef.current) sampleFileInputRef.current.value = '';
    },
  });

  const sampleDeleteMutation = useMutation({
    mutationFn: async () => {
      await api.delete('/profile/cover-letter-sample');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cover-letter-sample'] });
    },
  });

  function handleSampleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    if (selected) sampleUploadMutation.mutate(selected);
  }

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <Link to="/tracks" className="text-sm text-slate-400 hover:text-slate-200">← Back to tracks</Link>
      <h1 className="text-2xl font-semibold text-slate-100 mt-4 mb-2">Profile</h1>
      <p className="text-sm text-slate-400 mb-6">
        Upload a CV (PDF, DOCX, or TXT) to build or refresh your candidate profile. Parsing
        happens in the background and usually takes a few seconds.
      </p>

      <div className="bg-slate-900 rounded-lg p-6 max-w-xl">
        <label className="block text-sm text-slate-300 mb-2" htmlFor="cv-file-input">
          Choose CV file
        </label>
        <input
          id="cv-file-input"
          ref={fileInputRef}
          type="file"
          accept={SUPPORTED_EXTENSIONS.join(',')}
          onChange={handleFileChange}
          disabled={uploadMutation.isPending || isPolling}
          className="block w-full text-sm text-slate-300 file:mr-4 file:rounded file:border-0 file:bg-slate-800 file:px-4 file:py-2 file:text-slate-200 hover:file:bg-slate-700"
        />

        {selectError && <p className="text-sm text-red-400 mt-2">{selectError}</p>}

        <button
          onClick={handleUpload}
          disabled={!file || uploadMutation.isPending || isPolling}
          className="mt-4 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 disabled:text-slate-400 text-white text-sm rounded px-4 py-2 font-medium"
        >
          {uploadMutation.isPending ? 'Uploading…' : 'Upload CV'}
        </button>

        {uploadMutation.isError && (
          <p className="text-sm text-red-400 mt-3">
            Upload failed. Check the file and try again.
          </p>
        )}

        {uploadId && (
          <div className="mt-6 border-t border-slate-800 pt-4">
            <h2 className="text-sm font-medium text-slate-200 mb-2">Processing status</h2>

            {statusQuery.isLoading && !statusQuery.data && (
              <p className="text-sm text-slate-400">Checking status…</p>
            )}

            {status === 'processing' && (
              <p className="text-sm text-amber-400">
                Processing your CV… this page will update automatically.
              </p>
            )}

            {status === 'completed' && (
              <div>
                <p className="text-sm text-emerald-400">
                  Done. Your profile has been updated
                  {typeof statusQuery.data?.fields_extracted === 'number'
                    ? ` — ${statusQuery.data.fields_extracted} fields extracted.`
                    : '.'}
                </p>
                <button
                  onClick={handleUploadAnother}
                  className="mt-3 text-sm text-indigo-400 hover:text-indigo-300"
                >
                  Upload another CV
                </button>
              </div>
            )}

            {status === 'failed' && (
              <div>
                <p className="text-sm text-red-400">
                  Parsing failed{statusQuery.data?.error_message ? `: ${statusQuery.data.error_message}` : '.'}
                </p>
                <button
                  onClick={handleUploadAnother}
                  className="mt-3 text-sm text-indigo-400 hover:text-indigo-300"
                >
                  Try again
                </button>
              </div>
            )}

            {statusQuery.isError && (
              <p className="text-sm text-red-400">Failed to check status. It may still be processing.</p>
            )}
          </div>
        )}
      </div>

      <div className="bg-slate-900 rounded-lg p-6 max-w-xl mt-6">
        <h2 className="text-sm font-medium text-slate-200 mb-1">Cover letter style sample</h2>
        <p className="text-sm text-slate-400 mb-4">
          Upload a past cover letter to steer the tone and voice of future AI-generated ones.
          This is a style reference only — it's never stored as a real cover letter, never
          sent to an employer, and its facts are never copied into generated content.
        </p>

        {sampleQuery.isLoading && (
          <p className="text-sm text-slate-400">Checking for an existing sample…</p>
        )}

        {!sampleQuery.isLoading && sampleQuery.data && (
          <div className="mb-4 flex items-center justify-between bg-slate-800 rounded px-3 py-2">
            <div>
              <p className="text-sm text-slate-200">{sampleQuery.data.filename}</p>
              {sampleQuery.data.uploaded_at && (
                <p className="text-xs text-slate-500">
                  Uploaded {new Date(sampleQuery.data.uploaded_at).toLocaleDateString()}
                </p>
              )}
            </div>
            <button
              onClick={() => sampleDeleteMutation.mutate()}
              disabled={sampleDeleteMutation.isPending}
              className="text-xs text-red-400 hover:text-red-300 disabled:text-slate-600"
            >
              {sampleDeleteMutation.isPending ? 'Removing…' : 'Remove'}
            </button>
          </div>
        )}

        {!sampleQuery.isLoading && !sampleQuery.data && (
          <p className="text-sm text-slate-500 mb-4">
            No sample uploaded yet — cover letters use the default professional tone.
          </p>
        )}

        <label className="block text-sm text-slate-300 mb-2" htmlFor="sample-file-input">
          {sampleQuery.data ? 'Replace sample' : 'Choose sample cover letter'}
        </label>
        <input
          id="sample-file-input"
          ref={sampleFileInputRef}
          type="file"
          accept={SUPPORTED_EXTENSIONS.join(',')}
          onChange={handleSampleFileChange}
          disabled={sampleUploadMutation.isPending}
          className="block w-full text-sm text-slate-300 file:mr-4 file:rounded file:border-0 file:bg-slate-800 file:px-4 file:py-2 file:text-slate-200 hover:file:bg-slate-700"
        />

        {sampleUploadMutation.isPending && (
          <p className="text-sm text-amber-400 mt-2">Uploading…</p>
        )}
        {sampleUploadMutation.isError && (
          <p className="text-sm text-red-400 mt-2">Upload failed. Check the file and try again.</p>
        )}
        {sampleUploadMutation.isSuccess && (
          <p className="text-sm text-emerald-400 mt-2">Sample saved.</p>
        )}
      </div>
    </div>
  );
}

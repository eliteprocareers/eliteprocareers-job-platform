import { useParams, useLocation, Link } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../lib/api';
import type {
  DocType,
  GeneratedDocument,
  GenerateCVRequest,
  GenerateCoverLetterRequest,
  GenerateScreeningAnswerRequest,
  MatchWithJob,
} from '../lib/types';

interface JobSummary {
  job_title: string;
  job_company: string;
  job_url: string | null;
}

interface LocationState {
  job?: JobSummary;
}

// Known backend limitation (not fixed here): generated_documents.version is
// computed per (cv_track_id, doc_type) only -- there is no job_id column,
// so a "latest" document for a track cannot be trusted to belong to any
// particular job once more than one job has documents generated under the
// same track. Rather than call the /latest or list endpoints and risk
// silently showing another job's content as if it were this job's, this
// page only ever displays content that came back directly from a POST
// made on this page, in this session, for this exact job_id. Nothing is
// preloaded from history.
const DOC_LABELS: Record<DocType, string> = {
  cv: 'Tailored CV',
  cover_letter: 'Cover Letter',
  screening_answer: 'Screening Answer',
};

function formatContent(doc: GeneratedDocument): string {
  if (doc.doc_type !== 'cv') return doc.content;
  try {
    return JSON.stringify(JSON.parse(doc.content), null, 2);
  } catch {
    return doc.content;
  }
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded px-2 py-1"
    >
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

export default function TrackJobDocuments() {
  const { trackId, jobId } = useParams<{ trackId: string; jobId: string }>();
  const location = useLocation();
  const stateJob = (location.state as LocationState | null)?.job;

  const [docs, setDocs] = useState<Partial<Record<DocType, GeneratedDocument>>>({});
  const [errors, setErrors] = useState<Partial<Record<DocType, string>>>({});
  const [question, setQuestion] = useState('');
  const [wordLimit, setWordLimit] = useState<string>('');
  const [hadPriorJob, setHadPriorJob] = useState(false);
  const [lastJobId, setLastJobId] = useState(jobId);

  // Reset local state whenever the job changes, and note if this page had
  // already generated something for a *different* job in this session --
  // that's the concrete case the shared version counter can silently mangle.
  // Adjusted during render (not in an effect) per React's guidance for
  // resetting state in response to a prop change.
  if (jobId !== lastJobId) {
    setLastJobId(jobId);
    if (Object.keys(docs).length > 0) setHadPriorJob(true);
    setDocs({});
    setErrors({});
  }

  // Fallback if the page was opened directly (no router state): find the
  // job's title/company from the existing matches endpoint rather than
  // requiring a new backend endpoint just for this.
  const { data: matches } = useQuery({
    queryKey: ['matches', trackId],
    queryFn: async () => {
      const { data } = await api.get<MatchWithJob[]>(`/tracks/${trackId}/matches`, {
        params: { limit: 200 },
      });
      return data;
    },
    enabled: !!trackId && !stateJob,
  });

  const job: JobSummary | undefined =
    stateJob ?? matches?.find((m) => m.job_id === jobId) as JobSummary | undefined;

  function useGenerateMutation<TReq>(docType: DocType, path: string) {
    return useMutation({
      mutationFn: async (payload: TReq) => {
        const { data } = await api.post<GeneratedDocument>(
          `/tracks/${trackId}/${path}`,
          payload
        );
        return data;
      },
      onSuccess: (doc) => {
        setDocs((prev) => ({ ...prev, [docType]: doc }));
        setErrors((prev) => ({ ...prev, [docType]: undefined }));
      },
      onError: () => {
        setErrors((prev) => ({
          ...prev,
          [docType]: 'Generation failed. Try again in a moment.',
        }));
      },
    });
  }

  const cvMutation = useGenerateMutation<GenerateCVRequest>('cv', 'generate-cv');
  const coverLetterMutation = useGenerateMutation<GenerateCoverLetterRequest>(
    'cover_letter',
    'generate-cover-letter'
  );
  const screeningMutation = useGenerateMutation<GenerateScreeningAnswerRequest>(
    'screening_answer',
    'generate-screening-answer'
  );

  if (!trackId || !jobId) return null;

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <Link
        to={`/tracks/${trackId}/matches`}
        className="text-sm text-slate-400 hover:text-slate-200"
      >
        ← Back to matches
      </Link>

      <div className="mt-4 mb-2">
        <h1 className="text-2xl font-semibold text-slate-100">Generate documents</h1>
        {job ? (
          <p className="text-sm text-slate-400 mt-1">
            {job.job_url ? (
              <a href={job.job_url} target="_blank" rel="noreferrer" className="hover:underline">
                {job.job_title}
              </a>
            ) : (
              job.job_title
            )}
            {job.job_company ? ` · ${job.job_company}` : ''}
          </p>
        ) : (
          <p className="text-sm text-slate-500 mt-1">Loading job details...</p>
        )}
      </div>

      <div className="bg-amber-950/40 border border-amber-800/50 rounded-lg p-4 mb-6 text-sm text-amber-200">
        <p className="font-medium mb-1">Known limitation: document history isn't job-scoped yet</p>
        <p className="text-amber-300/90">
          Generated documents don't currently record which job they were made for, so a
          "previously generated" CV or cover letter can't be reliably matched back to this
          specific job once you've generated documents for more than one job under this track.
          Only documents generated below, in this session, are guaranteed to be for{' '}
          <span className="font-medium">this</span> job — always regenerate rather than trusting
          anything saved from before.
        </p>
        {hadPriorJob && (
          <p className="text-amber-300/90 mt-2 font-medium">
            You generated documents for a different job earlier in this session. Those are no
            longer shown here, and regenerating below will also become the new "latest" version
            for this track's document history — the earlier job's saved version may now be
            harder to tell apart from this one.
          </p>
        )}
      </div>

      <div className="space-y-6">
        {/* CV */}
        <DocumentCard
          title={DOC_LABELS.cv}
          isPending={cvMutation.isPending}
          error={errors.cv}
          doc={docs.cv}
          onGenerate={() => cvMutation.mutate({ job_id: jobId })}
          generateLabel={docs.cv ? 'Regenerate CV' : 'Generate CV'}
        />

        {/* Cover letter */}
        <DocumentCard
          title={DOC_LABELS.cover_letter}
          isPending={coverLetterMutation.isPending}
          error={errors.cover_letter}
          doc={docs.cover_letter}
          onGenerate={() => coverLetterMutation.mutate({ job_id: jobId })}
          generateLabel={docs.cover_letter ? 'Regenerate cover letter' : 'Generate cover letter'}
        />

        {/* Screening answer */}
        <div className="bg-slate-900 rounded-lg p-4">
          <h2 className="text-slate-100 font-medium mb-3">{DOC_LABELS.screening_answer}</h2>
          <div className="space-y-2 mb-3">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Paste the screening question, e.g. &quot;Why do you want to work here?&quot;"
              rows={2}
              className="w-full bg-slate-800 text-slate-100 rounded px-3 py-2 text-sm placeholder:text-slate-500"
            />
            <input
              type="number"
              min={1}
              value={wordLimit}
              onChange={(e) => setWordLimit(e.target.value)}
              placeholder="Word limit (optional)"
              className="w-48 bg-slate-800 text-slate-100 rounded px-3 py-2 text-sm placeholder:text-slate-500"
            />
          </div>
          <button
            onClick={() =>
              screeningMutation.mutate({
                job_id: jobId,
                question,
                word_limit: wordLimit ? Number(wordLimit) : undefined,
              })
            }
            disabled={screeningMutation.isPending || !question.trim()}
            className="text-sm bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded px-3 py-2 font-medium"
          >
            {screeningMutation.isPending
              ? 'Generating...'
              : docs.screening_answer
                ? 'Regenerate answer'
                : 'Generate answer'}
          </button>
          {errors.screening_answer && (
            <p className="text-red-400 text-sm mt-2">{errors.screening_answer}</p>
          )}
          {docs.screening_answer && (
            <div className="mt-3">
              <div className="flex justify-between items-center mb-1">
                <span className="text-xs text-slate-500">
                  Version {docs.screening_answer.version}
                </span>
                <CopyButton text={docs.screening_answer.content} />
              </div>
              <pre className="whitespace-pre-wrap text-sm text-slate-200 bg-slate-950 rounded p-3 max-h-96 overflow-auto">
                {docs.screening_answer.content}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function DocumentCard({
  title,
  isPending,
  error,
  doc,
  onGenerate,
  generateLabel,
}: {
  title: string;
  isPending: boolean;
  error?: string;
  doc?: GeneratedDocument;
  onGenerate: () => void;
  generateLabel: string;
}) {
  return (
    <div className="bg-slate-900 rounded-lg p-4">
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-slate-100 font-medium">{title}</h2>
        <button
          onClick={onGenerate}
          disabled={isPending}
          className="text-sm bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded px-3 py-2 font-medium"
        >
          {isPending ? 'Generating...' : generateLabel}
        </button>
      </div>
      {error && <p className="text-red-400 text-sm mb-2">{error}</p>}
      {doc && (
        <div>
          <div className="flex justify-between items-center mb-1">
            <span className="text-xs text-slate-500">Version {doc.version}</span>
            <CopyButton text={formatContent(doc)} />
          </div>
          <pre className="whitespace-pre-wrap text-sm text-slate-200 bg-slate-950 rounded p-3 max-h-96 overflow-auto">
            {formatContent(doc)}
          </pre>
        </div>
      )}
      {!doc && !isPending && (
        <p className="text-sm text-slate-500">Not generated yet in this session.</p>
      )}
    </div>
  );
}

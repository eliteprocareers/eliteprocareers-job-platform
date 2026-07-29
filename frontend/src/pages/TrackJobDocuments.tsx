import { useParams, useLocation, Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../lib/api';
import type {
  ApplicationStatus,
  ApplicationWithJob,
  CVContent,
  DocType,
  DocumentsBundle,
  GeneratedDocument,
  MatchWithJob,
  ScreeningAnswerRequest,
} from '../lib/types';
import ApplicationStatusBadge from '../components/ApplicationStatusBadge';
import { APPLICATION_STATUS_LABELS, APPLICATION_STATUS_ORDER } from '../lib/applicationStatus';

interface JobSummary {
  job_title: string;
  job_company: string;
  job_url: string | null;
}

interface LocationState {
  job?: JobSummary;
  backTo?: string;
  backLabel?: string;
}

// Versioning is now genuinely job-scoped on the backend (generated_documents
// has a job_id column, migration 0006) -- GET .../documents returns the
// latest of each type for this exact (track, job) pair, so it's safe to
// preload it on mount instead of only showing content generated fresh in
// this session. Rows created before job_id existed have job_id = NULL and
// won't show up here for any job -- not recoverable, not a bug in this page.
const DOC_LABELS: Record<DocType, string> = {
  cv: 'Tailored CV',
  cover_letter: 'Cover Letter',
  screening_answer: 'Screening Answer',
};

function formatContent(doc: GeneratedDocument): string {
  if (doc.doc_type !== 'cv') return doc.content;
  const parsed = parseCV(doc.content);
  return parsed ? cvToPlainText(parsed) : doc.content;
}

function parseCV(raw: string): CVContent | null {
  try {
    const obj = JSON.parse(raw);
    if (typeof obj?.summary !== 'string' || !Array.isArray(obj?.work_experience)) return null;
    return obj as CVContent;
  } catch {
    return null;
  }
}

function cvToPlainText(cv: CVContent): string {
  const lines: string[] = [];
  if (cv.summary) lines.push(cv.summary, '');
  if (cv.skills.length) {
    lines.push('SKILLS', cv.skills.join(', '), '');
  }
  if (cv.work_experience.length) {
    lines.push('WORK EXPERIENCE');
    for (const entry of cv.work_experience) {
      lines.push(`${entry.title} — ${entry.company} (${entry.dates})`);
      for (const bullet of entry.bullets) lines.push(`  • ${bullet}`);
      lines.push('');
    }
  }
  if (cv.education.length) lines.push('EDUCATION', ...cv.education, '');
  if (cv.certifications.length) lines.push('CERTIFICATIONS', ...cv.certifications, '');
  return lines.join('\n').trim();
}

function CvView({ cv }: { cv: CVContent }) {
  return (
    <div className="space-y-4 text-sm">
      {cv.summary && <p className="text-slate-200 leading-relaxed">{cv.summary}</p>}

      {cv.skills.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            Skills
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {cv.skills.map((skill, i) => (
              <span key={i} className="bg-slate-800 text-slate-300 rounded px-2 py-0.5 text-xs">
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      {cv.work_experience.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            Work experience
          </h3>
          <div className="space-y-3">
            {cv.work_experience.map((entry, i) => (
              <div key={i}>
                <div className="flex justify-between items-baseline">
                  <span className="text-slate-100 font-medium">{entry.title}</span>
                  <span className="text-xs text-slate-500">{entry.dates}</span>
                </div>
                <p className="text-slate-400 text-xs mb-1">{entry.company}</p>
                {entry.bullets.length > 0 && (
                  <ul className="list-disc list-inside text-slate-300 space-y-0.5">
                    {entry.bullets.map((bullet, j) => (
                      <li key={j}>{bullet}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {cv.education.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            Education
          </h3>
          <ul className="text-slate-300 space-y-0.5">
            {cv.education.map((entry, i) => (
              <li key={i}>{entry}</li>
            ))}
          </ul>
        </div>
      )}

      {cv.certifications.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
            Certifications
          </h3>
          <ul className="text-slate-300 space-y-0.5">
            {cv.certifications.map((entry, i) => (
              <li key={i}>{entry}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
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
  const { job: stateJob, backTo, backLabel } = (location.state as LocationState | null) ?? {};
  const queryClient = useQueryClient();

  const [errors, setErrors] = useState<Partial<Record<DocType, string>>>({});
  const [question, setQuestion] = useState('');
  const [wordLimit, setWordLimit] = useState<string>('');

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
    stateJob ?? (matches?.find((m) => m.job_id === jobId) as JobSummary | undefined);

  const bundleQueryKey = ['documents', trackId, jobId];
  const {
    data: bundle,
    isLoading: bundleLoading,
    error: bundleError,
  } = useQuery({
    queryKey: bundleQueryKey,
    queryFn: async () => {
      const { data } = await api.get<DocumentsBundle>(
        `/tracks/${trackId}/jobs/${jobId}/documents`
      );
      return data;
    },
    enabled: !!trackId && !!jobId,
  });

  const noMatch = Boolean(
    bundleError && (bundleError as { response?: { status?: number } })?.response?.status === 404
  );

  // No single-application-by-job endpoint exists on the backend -- the
  // only read is the track-wide list (GET /tracks/{track_id}/applications),
  // same reasoning as the matches fallback above: find this job's row
  // within it rather than requiring a new endpoint just for this page.
  const applicationsQueryKey = ['applications', trackId];
  const { data: applications, isLoading: applicationsLoading } = useQuery({
    queryKey: applicationsQueryKey,
    queryFn: async () => {
      const { data } = await api.get<ApplicationWithJob[]>(`/tracks/${trackId}/applications`);
      return data;
    },
    enabled: !!trackId,
  });
  const application = applications?.find((a) => a.job_id === jobId);
  const [applicationError, setApplicationError] = useState<string | null>(null);

  const createApplicationMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.post<ApplicationWithJob>(
        `/tracks/${trackId}/jobs/${jobId}/applications`,
        {}
      );
      return data;
    },
    onSuccess: (created) => {
      setApplicationError(null);
      queryClient.setQueryData<ApplicationWithJob[]>(applicationsQueryKey, (prev) => [
        ...(prev ?? []),
        { ...created, job_title: job?.job_title ?? '', job_company: job?.job_company ?? '', job_url: job?.job_url ?? null },
      ]);
      // Creating an application auto-links any already-generated documents
      // on the backend (application_id column) -- refetch the bundle so
      // this page reflects that link rather than showing stale state.
      queryClient.invalidateQueries({ queryKey: bundleQueryKey });
    },
    onError: () => setApplicationError('Failed to create application. Try again.'),
  });

  const updateApplicationStatusMutation = useMutation({
    mutationFn: async (status: ApplicationStatus) => {
      if (!application) throw new Error('No application to update');
      const { data } = await api.patch<ApplicationWithJob>(
        `/tracks/${trackId}/applications/${application.id}`,
        { status, notes: application.notes }
      );
      return data;
    },
    onSuccess: (updated) => {
      setApplicationError(null);
      queryClient.setQueryData<ApplicationWithJob[]>(applicationsQueryKey, (prev) =>
        prev?.map((a) => (a.id === updated.id ? { ...a, ...updated } : a))
      );
    },
    onError: () => setApplicationError('Failed to update status. Try again.'),
  });

  function useGenerateMutation<TReq = void>(docType: DocType, path: string) {
    return useMutation({
      mutationFn: async (payload: TReq) => {
        const { data } = await api.post<GeneratedDocument>(
          `/tracks/${trackId}/jobs/${jobId}/${path}`,
          payload
        );
        return data;
      },
      onSuccess: (doc) => {
        queryClient.setQueryData<DocumentsBundle>(bundleQueryKey, (prev) => ({
          cv: prev?.cv ?? null,
          cover_letter: prev?.cover_letter ?? null,
          screening_answer: prev?.screening_answer ?? null,
          [docType]: doc,
        }));
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

  const cvMutation = useGenerateMutation('cv', 'generate-cv');
  const coverLetterMutation = useGenerateMutation('cover_letter', 'generate-cover-letter');
  const screeningMutation = useGenerateMutation<ScreeningAnswerRequest>(
    'screening_answer',
    'generate-screening-answer'
  );

  if (!trackId || !jobId) return null;

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <Link
        to={`/tracks/${trackId}/matches`}
        state={{ backTo, backLabel }}
        className="text-sm text-slate-400 hover:text-slate-200"
      >
        ← Back to matches
      </Link>

      <div className="mt-4 mb-6">
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

      {noMatch && (
        <div className="bg-amber-950/40 border border-amber-800/50 rounded-lg p-4 mb-6 text-sm text-amber-200">
          No match exists yet between this track and this job, so documents can't be generated
          for it. Run matching for this track first, or open this page from a job in the matches
          list.
        </div>
      )}

      <div className="bg-slate-900 rounded-lg p-4 mb-6">
        <div className="flex justify-between items-center">
          <h2 className="text-slate-100 font-medium">Application status</h2>
          {application && <ApplicationStatusBadge status={application.status} />}
        </div>
        {applicationsLoading ? (
          <p className="text-sm text-slate-500 mt-2">Loading...</p>
        ) : application ? (
          <div className="mt-3 flex items-center gap-3">
            <label className="text-sm text-slate-400">
              Update status:{' '}
              <select
                value={application.status}
                disabled={updateApplicationStatusMutation.isPending}
                onChange={(e) =>
                  updateApplicationStatusMutation.mutate(e.target.value as ApplicationStatus)
                }
                className="ml-1 bg-slate-800 text-slate-200 rounded px-2 py-1 text-sm"
              >
                {APPLICATION_STATUS_ORDER.map((s) => (
                  <option key={s} value={s}>
                    {APPLICATION_STATUS_LABELS[s]}
                  </option>
                ))}
              </select>
            </label>
            <Link
              to={`/tracks/${trackId}/applications`}
              className="text-sm text-indigo-400 hover:text-indigo-300"
            >
              View all applications
            </Link>
          </div>
        ) : (
          <div className="mt-3">
            <p className="text-sm text-slate-500 mb-2">
              Not tracked yet. This only records status for your own reference — it never submits
              anything to the employer or an ATS on your behalf.
            </p>
            <button
              onClick={() => createApplicationMutation.mutate()}
              disabled={createApplicationMutation.isPending || noMatch}
              className="text-sm bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded px-3 py-2 font-medium"
            >
              {createApplicationMutation.isPending ? 'Creating...' : 'Track this application'}
            </button>
          </div>
        )}
        {applicationError && <p className="text-red-400 text-sm mt-2">{applicationError}</p>}
      </div>

      {bundleLoading && <p className="text-sm text-slate-500 mb-4">Loading saved documents...</p>}

      <div className="space-y-6">
        {/* CV */}
        <DocumentCard
          title={DOC_LABELS.cv}
          isPending={cvMutation.isPending}
          error={errors.cv}
          doc={bundle?.cv ?? undefined}
          onGenerate={() => cvMutation.mutate(undefined)}
          generateLabel={bundle?.cv ? 'Regenerate CV' : 'Generate CV'}
          disabled={noMatch}
        />

        {/* Cover letter */}
        <DocumentCard
          title={DOC_LABELS.cover_letter}
          isPending={coverLetterMutation.isPending}
          error={errors.cover_letter}
          doc={bundle?.cover_letter ?? undefined}
          onGenerate={() => coverLetterMutation.mutate(undefined)}
          generateLabel={bundle?.cover_letter ? 'Regenerate cover letter' : 'Generate cover letter'}
          disabled={noMatch}
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
                question,
                word_limit: wordLimit ? Number(wordLimit) : undefined,
              })
            }
            disabled={screeningMutation.isPending || !question.trim() || noMatch}
            className="text-sm bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded px-3 py-2 font-medium"
          >
            {screeningMutation.isPending
              ? 'Generating...'
              : bundle?.screening_answer
                ? 'Regenerate answer'
                : 'Generate answer'}
          </button>
          {errors.screening_answer && (
            <p className="text-red-400 text-sm mt-2">{errors.screening_answer}</p>
          )}
          {bundle?.screening_answer && (
            <div className="mt-3">
              <div className="flex justify-between items-center mb-1">
                <span className="text-xs text-slate-500">
                  Version {bundle.screening_answer.version}
                </span>
                <CopyButton text={bundle.screening_answer.content} />
              </div>
              <pre className="whitespace-pre-wrap text-sm text-slate-200 bg-slate-950 rounded p-3 max-h-96 overflow-auto">
                {bundle.screening_answer.content}
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
  disabled,
}: {
  title: string;
  isPending: boolean;
  error?: string;
  doc?: GeneratedDocument;
  onGenerate: () => void;
  generateLabel: string;
  disabled?: boolean;
}) {
  const cv = doc?.doc_type === 'cv' ? parseCV(doc.content) : null;

  return (
    <div className="bg-slate-900 rounded-lg p-4">
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-slate-100 font-medium">{title}</h2>
        <button
          onClick={onGenerate}
          disabled={isPending || disabled}
          className="text-sm bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded px-3 py-2 font-medium"
        >
          {isPending ? 'Generating...' : generateLabel}
        </button>
      </div>
      {error && <p className="text-red-400 text-sm mb-2">{error}</p>}
      {doc && (
        <div>
          <div className="flex justify-between items-center mb-2">
            <span className="text-xs text-slate-500">Version {doc.version}</span>
            <CopyButton text={formatContent(doc)} />
          </div>
          {doc.doc_type === 'cv' ? (
            cv ? (
              <div className="bg-slate-950 rounded p-4 max-h-[32rem] overflow-auto">
                <CvView cv={cv} />
              </div>
            ) : (
              <>
                <p className="text-amber-400 text-xs mb-2">
                  Couldn't parse this as structured CV content — showing raw response.
                </p>
                <pre className="whitespace-pre-wrap text-sm text-slate-200 bg-slate-950 rounded p-3 max-h-96 overflow-auto">
                  {doc.content}
                </pre>
              </>
            )
          ) : (
            <pre className="whitespace-pre-wrap text-sm text-slate-200 bg-slate-950 rounded p-3 max-h-96 overflow-auto">
              {doc.content}
            </pre>
          )}
        </div>
      )}
      {!doc && !isPending && (
        <p className="text-sm text-slate-500">Not generated yet.</p>
      )}
    </div>
  );
}

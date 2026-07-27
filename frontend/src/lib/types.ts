export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user_id: string;
  email: string | null;
}

export interface CVTrack {
  id?: string;
  user_id: string;
  track_name: string;
  target_roles: string[];
  scoring_weights: Record<string, number>;
  preferred_locations: string[];
  preferred_countries: string[];
  employment_types: string[];
  seniority_levels: string[];
  industries: string[];
  work_mode: string[];
  willing_to_relocate: boolean;
  visa_sponsorship_required: boolean | null;
  work_authorization_status: string | null;
  salary_expectation_min: number | null;
  salary_expectation_max: number | null;
  salary_currency: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface CreateTrackRequest {
  track_name: string;
  target_roles: string[];
  scoring_weights?: Record<string, number>;
  preferred_locations: string[];
  preferred_countries: string[];
  employment_types: string[];
  seniority_levels: string[];
  industries: string[];
  work_mode: string[];
  willing_to_relocate: boolean;
  visa_sponsorship_required: boolean | null;
  work_authorization_status: string | null;
  salary_expectation_min: number | null;
  salary_expectation_max: number | null;
  salary_currency: string | null;
}

export type UpdateTrackRequest = Partial<CreateTrackRequest>;

export interface MatchTriggerResponse {
  track_id: string;
  track_name: string;
  status: string;
  message: string;
}

export interface MatchWithJob {
  match_id: string;
  job_id: string;
  match_score: number | null;
  ai_rationale: string | null;
  scored_at: string | null;
  job_title: string;
  job_company: string;
  job_url: string | null;
  job_location: string | null;
}

export interface CVUploadTriggerResponse {
  upload_id: string;
  filename: string;
  status: string;
  message: string;
}

export type CVUploadStatus = 'processing' | 'completed' | 'failed';

export interface CVUpload {
  id?: string;
  user_id: string;
  filename: string;
  file_size_bytes: number;
  status: CVUploadStatus;
  raw_text?: string | null;
  fields_extracted?: number | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface CoverLetterStyleSample {
  id?: string;
  user_id: string;
  filename: string;
  sample_text: string;
  uploaded_at?: string | null;
}

export type DocType = 'cv' | 'cover_letter' | 'screening_answer';

export interface GeneratedDocument {
  id?: string;
  user_id: string;
  cv_track_id: string;
  job_id?: string | null;
  application_id?: string | null;
  doc_type: DocType;
  content: string;
  version: number;
  ai_model_used?: string | null;
  created_at?: string;
}

export interface ScreeningAnswerRequest {
  question: string;
  word_limit?: number | null;
}

export interface DocumentsBundle {
  cv: GeneratedDocument | null;
  cover_letter: GeneratedDocument | null;
  screening_answer: GeneratedDocument | null;
}

export type ApplicationStatus =
  | 'draft'
  | 'submitted'
  | 'interviewing'
  | 'rejected'
  | 'offer'
  | 'withdrawn';

export interface Application {
  id?: string;
  user_id: string;
  job_id: string;
  cv_track_id: string;
  status: ApplicationStatus;
  applied_at: string | null;
  notes: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface ApplicationWithJob {
  id: string;
  job_id: string;
  cv_track_id: string;
  status: ApplicationStatus;
  applied_at: string | null;
  notes: string | null;
  created_at: string | null;
  job_title: string;
  job_company: string;
  job_url: string | null;
}

export interface CreateApplicationRequest {
  notes?: string | null;
}

export interface UpdateApplicationStatusRequest {
  status: ApplicationStatus;
  notes?: string | null;
}

export interface CVWorkExperienceEntry {
  title: string;
  company: string;
  dates: string;
  bullets: string[];
}

export interface CVContent {
  summary: string;
  skills: string[];
  work_experience: CVWorkExperienceEntry[];
  education: string[];
  certifications: string[];
}

// ---------------------------------------------------------------------
// Organizations / invites (Phase 4)
// ---------------------------------------------------------------------

export type OrgType =
  | 'individual'
  | 'agency'
  | 'staffing_firm'
  | 'company'
  | 'university'
  | 'career_coaching_firm'
  | 'enterprise';

export type MemberRole = 'owner' | 'admin' | 'member';

// Roles that can actually be granted via invite -- deliberately
// excludes 'owner', matching the backend's InvitableRole.
export type InvitableRole = 'admin' | 'member';

export type InviteStatus = 'pending' | 'accepted' | 'revoked' | 'expired';

export interface Organization {
  id: string;
  name: string;
  org_type: OrgType;
  created_at: string;
  updated_at: string;
}

export interface OrganizationMember {
  id: string;
  organization_id: string;
  user_id: string;
  role: MemberRole;
  created_at: string;
}

// Admin-facing view of an invite -- deliberately has no `token` field.
// The token is only ever present on OrganizationInviteCreated, right
// after creation -- see that type and the backend comment it mirrors.
export interface OrganizationInvite {
  id: string;
  organization_id: string;
  email: string;
  role: InvitableRole;
  status: InviteStatus;
  invited_by: string;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
}

export interface OrganizationInviteCreated extends OrganizationInvite {
  token: string;
}

// Unauthenticated-safe preview by token, backed by get_invite_preview().
export interface InvitePreview {
  organization_name: string;
  email: string;
  role: InvitableRole;
  status: InviteStatus;
  expires_at: string;
}

export interface CreateOrganizationRequest {
  name: string;
  org_type: OrgType;
}

export interface CreateInviteRequest {
  email: string;
  role: InvitableRole;
}

export interface SignupRequest {
  email: string;
  password: string;
}

export interface SignupResponse {
  user_id: string;
  email: string | null;
  access_token: string | null;
  refresh_token: string | null;
  requires_confirmation: boolean;
}

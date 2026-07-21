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

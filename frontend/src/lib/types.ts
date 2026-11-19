export type Theme = "light" | "dark" | "system";

export type ApplicationStatus =
  | "saved"
  | "applied"
  | "screening"
  | "interviewing"
  | "offer"
  | "accepted"
  | "rejected"
  | "withdrawn"
  | "ghosted";

export type WorkMode = "onsite" | "hybrid" | "remote";
export type EmploymentType = "full_time" | "part_time" | "contract" | "internship";
export type SalaryPeriod = "year" | "month" | "day" | "hour";
export type EventType = "created" | "status_change" | "updated" | "note" | "archived";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface OwnerProfile {
  id: string;
  email: string;
  full_name: string | null;
  timezone: string;
  currency: string;
  theme: Theme;
  last_login_at: string | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_at: string;
  owner: OwnerProfile;
}

export interface SessionView {
  id: string;
  user_agent: string | null;
  ip: string | null;
  created_at: string;
  last_used_at: string | null;
  expires_at: string;
  revoked_at: string | null;
  current: boolean;
}

export interface MetaResponse {
  app_name: string;
  owner_configured: boolean;
  ai_configured: boolean;
  environment: string;
  version: string;
}

export interface CompanyRef {
  id: string;
  name: string;
}

export interface Company {
  id: string;
  name: string;
  website: string | null;
  industry: string | null;
  location: string | null;
  notes: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  application_count: number;
  job_description_count: number;
}

export interface CompanyOption {
  id: string;
  name: string;
  archived_at: string | null;
}

export interface CompanyInput {
  name: string;
  website?: string | null;
  industry?: string | null;
  location?: string | null;
  notes?: string | null;
}

export interface JobDescriptionListItem {
  id: string;
  title: string;
  location: string | null;
  seniority: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  company: CompanyRef;
  text_chars: number;
}

export interface JobDescription {
  id: string;
  title: string;
  location: string | null;
  url: string | null;
  raw_text: string;
  seniority: string | null;
  employment_type: string | null;
  required_skills: string[] | null;
  preferred_skills: string[] | null;
  responsibilities: string[] | null;
  notes: string | null;
  source_file_id: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  company: CompanyRef;
}

export interface JobDescriptionInput {
  company_id: string;
  title: string;
  location?: string | null;
  url?: string | null;
  raw_text?: string;
  notes?: string | null;
  seniority?: string | null;
  employment_type?: string | null;
  required_skills?: string[] | null;
  preferred_skills?: string[] | null;
  responsibilities?: string[] | null;
}

export interface ResumeVersionRef {
  id: string;
  version_no: number;
  label: string | null;
}

export interface Resume {
  id: string;
  name: string;
  headline: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  version_count: number;
  current_version_no: number | null;
  current_file_name: string | null;
}

export interface ResumeVersion {
  id: string;
  version_no: number;
  label: string | null;
  notes: string | null;
  created_at: string;
  file_id: string;
  extracted_chars: number;
  is_current: boolean;
}

export interface ResumeDetail extends Resume {
  versions: ResumeVersion[];
}

export interface ResumeUsage {
  application_count: number;
  analysis_count: number;
}

export interface Application {
  id: string;
  title: string;
  status: ApplicationStatus;
  location: string | null;
  work_mode: WorkMode | null;
  employment_type: EmploymentType | null;
  job_url: string | null;
  applied_on: string | null;
  salary_min: string | null;
  salary_max: string | null;
  salary_currency: string | null;
  salary_period: SalaryPeriod | null;
  source: string | null;
  follow_up_on: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  company: CompanyRef;
  job_description: { id: string; title: string } | null;
  resume_version: ResumeVersionRef | null;
}

export interface TimelineEvent {
  id: string;
  type: EventType;
  from_status: string | null;
  to_status: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface ApplicationDetail extends Application {
  notes: string | null;
  rejection_reason: string | null;
  offer_amount: string | null;
  offer_deadline: string | null;
  jd_id: string | null;
  resume_version_id: string | null;
  events: TimelineEvent[];
}

export interface KanbanColumn {
  status: ApplicationStatus;
  count: number;
  items: Application[];
}

export interface KanbanBoard {
  columns: KanbanColumn[];
}

export interface ApplicationInput {
  company_id: string;
  title: string;
  jd_id?: string | null;
  resume_version_id?: string | null;
  location?: string | null;
  employment_type?: EmploymentType | null;
  work_mode?: WorkMode | null;
  job_url?: string | null;
  status?: ApplicationStatus;
  applied_on?: string | null;
  salary_min?: string | number | null;
  salary_max?: string | number | null;
  salary_currency?: string | null;
  salary_period?: SalaryPeriod | null;
  source?: string | null;
  notes?: string | null;
  follow_up_on?: string | null;
  duplicate_override?: boolean;
}

export type ApplicationUpdate = Partial<Omit<ApplicationInput, "duplicate_override">> & {
  rejection_reason?: string | null;
  offer_amount?: string | number | null;
  offer_deadline?: string | null;
};

export interface StatusCount {
  status: ApplicationStatus;
  count: number;
}

export interface ConversionMetric {
  numerator: number;
  denominator: number;
  rate: number | null;
  label: string;
}

export interface Dashboard {
  total_applications: number;
  active_applications: number;
  archived_applications: number;
  by_status: StatusCount[];
  by_company: { company_id: string; company_name: string; count: number }[];
  offers: number;
  rejections: number;
  interviews_scheduled: number;
  response: ConversionMetric;
  interview_conversion: ConversionMetric;
  offer_conversion: ConversionMetric;
  follow_ups: { due_today: number; overdue: number; upcoming: number; completed: number };
  tasks: { pending: number; overdue: number; due_today: number; completed_this_week: number };
  upcoming_interviews: {
    id: string;
    application_id: string;
    application_title: string;
    company_name: string;
    round_no: number;
    type: string;
    scheduled_at: string;
    timezone: string;
  }[];
  recent_activity: {
    id: string;
    application_id: string;
    application_title: string;
    company_name: string;
    type: string;
    from_status: string | null;
    to_status: string | null;
    created_at: string;
  }[];
  applications_trend: { bucket: string; count: number }[];
  average_days_to_response: number | null;
  applied_this_week: number;
  applied_this_month: number;
}

export type TaskStatus = "todo" | "in_progress" | "done";
export type TaskPriority = "low" | "medium" | "high";
export type FollowUpChannel = "email" | "linkedin" | "phone" | "other";
export type FollowUpStatus = "pending" | "done" | "skipped";
export type InterviewType =
  | "phone"
  | "video"
  | "onsite"
  | "technical"
  | "behavioral"
  | "panel"
  | "other";
export type InterviewOutcome = "pending" | "passed" | "failed" | "cancelled" | "no_show";
export type AnalysisStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "stale";
export type FindingKind = "resume_evidence" | "jd_requirement" | "inferred_recommendation";

export interface ApplicationRef {
  id: string;
  title: string;
  company_name: string;
}

export interface Task {
  id: string;
  title: string;
  description: string | null;
  priority: TaskPriority;
  status: TaskStatus;
  due_on: string | null;
  completed_at: string | null;
  is_overdue: boolean;
  application: ApplicationRef | null;
  created_at: string;
  updated_at: string;
}

export interface TaskInput {
  title: string;
  description?: string | null;
  priority?: TaskPriority;
  status?: Exclude<TaskStatus, "done">;
  due_on?: string | null;
  application_id?: string | null;
}

export interface FollowUp {
  id: string;
  application: ApplicationRef;
  due_on: string;
  channel: FollowUpChannel;
  status: FollowUpStatus;
  done_at: string | null;
  is_overdue: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface FollowUpInput {
  application_id: string;
  due_on: string;
  channel?: FollowUpChannel;
  notes?: string | null;
}

export interface Interview {
  id: string;
  application: ApplicationRef;
  round_no: number;
  type: InterviewType;
  scheduled_at: string;
  timezone: string;
  interviewer: string | null;
  location: string | null;
  link: string | null;
  prep_notes: string | null;
  outcome: InterviewOutcome;
  feedback: string | null;
  is_upcoming: boolean;
  created_at: string;
  updated_at: string;
}

export interface InterviewInput {
  application_id: string;
  round_no?: number | null;
  type?: InterviewType;
  scheduled_at: string;
  timezone?: string;
  interviewer?: string | null;
  location?: string | null;
  link?: string | null;
  prep_notes?: string | null;
}

export interface TimeEntry {
  id: string;
  task_id: string | null;
  task_title: string | null;
  started_at: string;
  ended_at: string | null;
  duration_minutes: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface TimeEntryInput {
  started_at: string;
  ended_at?: string | null;
  task_id?: string | null;
  notes?: string | null;
}

export interface Finding {
  kind: FindingKind;
  category: string;
  label: string;
  detail: string;
  evidence: string | null;
}

export interface AnalysisResult {
  score: number;
  summary: string;
  alignment_explanation: string;
  findings: Finding[];
  schema_version: string;
  created_at: string;
}

export interface AnalysisJob {
  id: string;
  status: AnalysisStatus;
  resume_version: {
    id: string;
    resume_id: string;
    resume_name: string;
    version_no: number;
    label: string | null;
  };
  job_description: { id: string; title: string; company_name: string | null } | null;
  jd_excerpt: string | null;
  provider: string;
  model: string;
  prompt_version: string;
  attempts: number;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  result: AnalysisResult | null;
}

export interface AnalysisStats {
  total: number;
  succeeded: number;
  failed: number;
  running: number;
  average_score: number | null;
}

export interface ResumeScore {
  resume_version_id: string;
  resume_name: string;
  version_no: number;
  label: string | null;
  analyses: number;
  average_score: number;
}

export interface Analytics {
  generated_at: string;
  total_applications: number;
  active_applications: number;
  submitted: number;
  by_status: StatusCount[];
  by_company: { company_id: string; company_name: string; count: number }[];
  by_source: { source: string; count: number }[];
  response: ConversionMetric;
  interview_conversion: ConversionMetric;
  offer_conversion: ConversionMetric;
  applications_weekly: { week: string; count: number }[];
  applications_monthly: { month: string; count: number }[];
  average_days_to_response: number | null;
  follow_up_performance: {
    total_due: number;
    completed_on_time: number;
    completed: number;
    skipped: number;
    pending: number;
    pending_overdue: number;
    rate: number | null;
    label: string;
  };
  tasks_completed_weekly: { week: string; count: number }[];
  time_logged_weekly: { week: string; minutes: number }[];
  analysis_history: {
    job_id: string;
    score: number;
    created_at: string;
    resume_version_id: string;
    resume_name: string;
    version_no: number;
    label: string | null;
    jd_title: string | null;
  }[];
  resume_alignment: ResumeScore[];
  average_alignment: number | null;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: unknown;
    request_id?: string;
  };
}

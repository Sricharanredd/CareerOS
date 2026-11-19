import type {
  ApplicationStatus,
  EmploymentType,
  FollowUpChannel,
  FollowUpStatus,
  InterviewOutcome,
  InterviewType,
  SalaryPeriod,
  TaskPriority,
  TaskStatus,
  WorkMode,
} from "@/lib/types";

export const STATUS_ORDER: ApplicationStatus[] = [
  "saved",
  "applied",
  "screening",
  "interviewing",
  "offer",
  "accepted",
  "rejected",
  "withdrawn",
  "ghosted",
];

export const ACTIVE_STATUSES: ApplicationStatus[] = [
  "saved",
  "applied",
  "screening",
  "interviewing",
  "offer",
];

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  saved: "Saved",
  applied: "Applied",
  screening: "Screening",
  interviewing: "Interviewing",
  offer: "Offer",
  accepted: "Accepted",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
  ghosted: "Ghosted",
};

/** Mirrors app/db/enums.py ALLOWED_TRANSITIONS. */
export const ALLOWED_TRANSITIONS: Record<ApplicationStatus, ApplicationStatus[]> = {
  saved: ["applied", "withdrawn"],
  applied: ["screening", "interviewing", "rejected", "withdrawn", "ghosted"],
  screening: ["interviewing", "rejected", "withdrawn", "ghosted"],
  interviewing: ["offer", "rejected", "withdrawn", "ghosted"],
  offer: ["accepted", "rejected", "withdrawn"],
  accepted: [],
  rejected: [],
  withdrawn: [],
  ghosted: [],
};

export const STATUS_TONE: Record<ApplicationStatus, string> = {
  saved: "bg-surface-3 text-muted border-line-strong",
  applied: "bg-accent-soft text-accent border-accent/25",
  screening: "bg-warning-soft text-warning border-warning/25",
  interviewing: "bg-teal-soft text-teal border-teal/25",
  offer: "bg-success-soft text-success border-success/30",
  accepted: "bg-success-soft text-success border-success/40",
  rejected: "bg-danger-soft text-danger border-danger/25",
  withdrawn: "bg-surface-2 text-subdued border-line",
  ghosted: "bg-surface-2 text-subdued border-dashed border-line-strong",
};

export const STATUS_DOT: Record<ApplicationStatus, string> = {
  saved: "bg-subdued",
  applied: "bg-accent",
  screening: "bg-warning",
  interviewing: "bg-teal",
  offer: "bg-success",
  accepted: "bg-success",
  rejected: "bg-danger",
  withdrawn: "bg-line-strong",
  ghosted: "bg-subdued",
};

export const WORK_MODE_LABEL: Record<WorkMode, string> = {
  onsite: "On-site",
  hybrid: "Hybrid",
  remote: "Remote",
};

export const EMPLOYMENT_TYPE_LABEL: Record<EmploymentType, string> = {
  full_time: "Full-time",
  part_time: "Part-time",
  contract: "Contract",
  internship: "Internship",
};

export const SALARY_PERIOD_LABEL: Record<SalaryPeriod, string> = {
  year: "year",
  month: "month",
  day: "day",
  hour: "hour",
};

export const COMPANY_SORTS = [
  { value: "name", label: "Name A–Z" },
  { value: "-name", label: "Name Z–A" },
  { value: "-created_at", label: "Newest first" },
];

export const APPLICATION_SORTS = [
  { value: "-created_at", label: "Newest first" },
  { value: "-applied_on", label: "Applied (latest)" },
  { value: "applied_on", label: "Applied (earliest)" },
  { value: "-updated_at", label: "Recently updated" },
  { value: "title", label: "Title A–Z" },
];

export const CURRENCY_OPTIONS = [
  "USD", "EUR", "GBP", "INR", "AUD", "CAD", "SGD", "AED", "JPY", "CHF", "NZD", "ZAR",
] as const;

export const COMMON_TIMEZONES = [
  "UTC",
  "Asia/Kolkata",
  "Asia/Dubai",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
  "Europe/London",
  "Europe/Berlin",
  "Europe/Paris",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Sao_Paulo",
];

export const PAGE_SIZE = 20;

export const TASK_PRIORITY_LABEL: Record<TaskPriority, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
};

export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  done: "Done",
};

export const FOLLOW_UP_CHANNEL_LABEL: Record<FollowUpChannel, string> = {
  email: "Email",
  linkedin: "LinkedIn",
  phone: "Phone",
  other: "Other",
};

export const FOLLOW_UP_STATUS_LABEL: Record<FollowUpStatus, string> = {
  pending: "Pending",
  done: "Done",
  skipped: "Skipped",
};

export const INTERVIEW_TYPE_LABEL: Record<InterviewType, string> = {
  phone: "Phone screen",
  video: "Video call",
  onsite: "On-site",
  technical: "Technical",
  behavioral: "Behavioural",
  panel: "Panel",
  other: "Other",
};

export const INTERVIEW_OUTCOME_LABEL: Record<InterviewOutcome, string> = {
  pending: "Pending",
  passed: "Passed",
  failed: "Failed",
  cancelled: "Cancelled",
  no_show: "No show",
};

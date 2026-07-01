// ── Shared TypeScript Types ────────────────────────────────────────────────────

export interface UserProfile {
  name: string;
  email: string;
  picture: string;
  sub: string;
}

export interface AppConfig {
  google_client_id: string;
  google_redirect_uri: string;
}

export interface ProfileResponse {
  authenticated: boolean;
  profile: UserProfile | null;
  token?: string;
}

export type PipelineStatus = 'idle' | 'running' | 'completed' | 'error';

export interface HitlInfo {
  mid_login_fields: boolean;
  fields: Array<{ name: string; type: string; placeholder?: string }>;
  escape_options: string[];
}

export interface SourceInfo {
  source: 'local' | 'drive' | 'sheets';
  filename: string;
  file_id?: string;
  sheet_url?: string;
}

export interface StatusResponse {
  status: PipelineStatus;
  error: string | null;
  logs: string;
  hitl: HitlInfo | null;
  apk_info: SourceInfo | null;
  schema_info: SourceInfo | null;
}

export interface SheetData {
  headers: string[];
  rows: Record<string, string | number>[];
}

export interface ResultsResponse {
  sheets: string[];
  data: Record<string, SheetData>;
}

export type StatusCell =
  | 'Implemented'
  | 'Implemented with issues'
  | 'Not Implemented'
  | 'Scenario Not Found';

export interface RowChange {
  status?: StatusCell;
  comments?: string;
  logs?: string;
}

export interface SaveEditsPayload {
  sheet: string;
  rows: Record<string, RowChange>;
}

export interface ActivityLabel {
  running: string;
  done: string;
}

// Tool call information
export interface ToolCallInfo {
  id: string;
  name: string;
  parameters: Record<string, any>;
  result?: string | null;
  error?: string | null;
  result_summary?: string | null;
  approved?: boolean | null;
  nested_tool_calls?: ToolCallInfo[] | null;
}

// Deep research section
export interface DeepResearchSection {
  category: string;
  subtopic: string;
  content: string;
}

// Taxonomy types
export interface TaxonomySubTopic {
  name: string;
  description: string;
  search_queries: string[];
  sections: any[];
}

export interface TaxonomyCategory {
  name: string;
  description: string;
  sub_topics: TaxonomySubTopic[];
}

export interface ResearchTaxonomy {
  taxonomy: TaxonomyCategory[];
  confidence: string;
  known_gaps: string[];
}

// Search result item from search_done event
export interface SearchResultItem {
  title: string;
  url: string;
  domain: string;
}

// Maintenance-copilot structured answer (from the maintenance_answer event)
export type MaintenanceAnswerType = 'extractive' | 'synthesized' | 'clarification_needed';

export interface MaintenanceCitation {
  chunk_id: string;
  doc: string;
  revision: string;
  ata: string;
  citation: string;          // human-readable locator (chip tooltip)
  source_id: string;
  source_name: string;       // filename, e.g. amm_ata32.md
  page_number: number | null; // null until page-bearing (PDF/OCR) ingestion
  confidence_score: number;  // 0..1 retrieval score of the cited chunk
  // Click-through target: module-relative source path + offsets of the
  // verified quote within the cited chunk's text.
  source_path?: string;
  char_start?: number | null;
  char_end?: number | null;
}

// Message types


// Structured todo item (mirrors backend TodoHandler.to_payload())
export type TodoStatus = 'todo' | 'doing' | 'done';

export interface Todo {
  id: string;
  title: string;
  status: TodoStatus;
  active_form?: string;
}

export interface Message {
  role: 'user' | 'assistant' | 'system' | 'tool_call' | 'tool_result' | 'thinking' | 'search_result' | 'maintenance_answer' | 'deep_research' | 'image_message' | 'custom_block' | 'todos';
  // live todo list (role === 'todos')
  todos?: Todo[];
  // custom_block fields
  block_id?: string;
  block_module?: string;
  block_file?: string;
  block_src?: string;
  block_props?: Record<string, any>;
  block_height?: number | 'auto';
  block_title?: string;
  content: string;
  timestamp?: string;
  // Groups all assistant text chunks from a single agent turn into one bubble,
  // even when tool_call/tool_result messages are interleaved between chunks.
  turnId?: string;
  tool_call_id?: string;
  tool_name?: string;
  tool_args?: Record<string, any>;
  tool_result?: any;
  tool_args_display?: string | null;
  activity?: ActivityLabel | null;
  tool_summary?: string | string[] | null;
  tool_success?: boolean;
  tool_error?: string | null;
  tool_calls?: ToolCallInfo[];
  metadata?: Record<string, any>;
  depth?: number;
  parent_tool_call_id?: string;
  thinking_trace?: string | null;
  reasoning_content?: string | null;
  streaming?: boolean;
  // search_result fields
  search_query?: string;
  search_result_count?: number;
  search_results?: SearchResultItem[];
  search_provider?: string;
  // maintenance_answer fields (from the maintenance_copilot skill tool)
  ma_answer?: string;               // response.primary_answer
  ma_answer_type?: MaintenanceAnswerType;
  ma_exact_quote?: string | null;   // verbatim substring of the cited source
  ma_is_sensitive?: boolean;
  ma_citations?: MaintenanceCitation[];
  ma_related_suggestions?: string[];
  ma_needs_user_input?: boolean;
  ma_missing_fields?: string[];
  ma_confidence?: number;
  ma_confidence_band?: 'high' | 'medium' | 'low';
  ma_review_required?: boolean;
  ma_advisory_note?: string;
  ma_validation_warnings?: string[];
  // deep_research fields
  dr_job_id?: string;
  dr_topic?: string;
  dr_taxonomy?: ResearchTaxonomy;
  dr_progress?: number;
  dr_sections?: DeepResearchSection[];
  dr_active_section?: { category: string; subtopic: string };
  dr_status?: 'reviewing' | 'queued' | 'running' | 'done' | 'error';
  dr_error?: string;
  dr_review_request_id?: string;
  dr_report_path?: string;
  // image_message fields
  image_src?: string;
  image_mime?: string;
  image_caption?: string;
}

// Session types
export interface Session {
  id: string;
  working_dir: string;  // Backend returns this key even though model has working_directory
  created_at: string;
  updated_at: string;
  message_count: number;
  token_usage: Record<string, number>;
  title?: string;
  has_session_model?: boolean;
}

// Configuration types
export interface Config {
  model: string;
  model_thinking?: string | null;
  model_vlm?: string | null;
  model_critique?: string | null;
  model_compact?: string | null;
  api_base_url?: string | null;
  api_key: string | null;
  temperature: number;
  enable_bash: boolean;
  working_directory: string;
}

// Parallel solver WS payload shapes
export interface ParallelSolverStartedData {
  job_id: string;
  n: number;
  task: string;
  worktree_names: string[];
  session_id: string;
}

export interface ParallelSolverProgressData {
  job_id: string;
  done: number;
  n: number;
  session_id: string;
}

export interface ParallelSolverCandidateData {
  thread: number;
  ok: boolean;
  summary: string;
}

export interface ParallelSolverDoneData {
  job_id: string;
  status: string;
  applied: boolean;
  winner_thread: number;
  reasoning: string;
  conflicted_files: string[];
  dropped_threads: number[];
  candidates: ParallelSolverCandidateData[];
  session_id: string;
}

// WebSocket event types
export interface WSMessage {
  type: 'user_message' | 'message_start' | 'message_chunk' | 'message_complete' | 'tool_call' | 'tool_result' | 'approval_required' | 'approval_resolved' | 'error' | 'pong' | 'mcp_status_update' | 'mcp_servers_update' | 'connected' | 'disconnected' | 'thinking_block' | 'thinking' | 'thinking_done' | 'search_done' | 'status_update' | 'ask_user_required' | 'ask_user_resolved' | 'session_activity' | 'plan_approval_required' | 'plan_approval_resolved' | 'plan_content' | 'subagent_start' | 'subagent_complete' | 'todos_updated' | 'parallel_agents_start' | 'parallel_agents_done' | 'parallel_solver_started' | 'parallel_solver_progress' | 'parallel_solver_done' | 'divide_job_started' | 'divide_task_update' | 'divide_job_done' | 'task_completed' | 'progress' | 'nested_tool_call' | 'nested_tool_result' | 'deep_research_taxonomy_ready' | 'deep_research_queued' | 'deep_research_start' | 'deep_research_section_start' | 'deep_research_section_done' | 'deep_research_done' | 'deep_research_error' | 'image_message' | 'custom_block' | 'custom_block_update' | 'custom_block_remove' | 'block_rpc_result' | 'session_messages_replaced' | 'blackboard.note' | 'blackboard.request' | 'blackboard.bid' | 'blackboard.response' | 'maintenance_answer';
  data: any;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, any>;
  requiresApproval: boolean;
}

export interface ApprovalRequest {
  id: string;
  tool_name: string;
  arguments: Record<string, any>;
  description: string;
  preview?: string;
}

// Status bar info
export interface StatusInfo {
  mode: 'normal' | 'plan';
  autonomy_level: 'Manual' | 'Semi-Auto' | 'Auto';
  thinking_level?: 'Off' | 'Low' | 'Medium' | 'High';
  model?: string;
  working_dir?: string;
  git_branch?: string | null;
  session_cost?: number;
  context_usage_pct?: number;
  simple_mode?: boolean;
}

// Ask-user question types
export interface AskUserOption {
  label: string;
  description: string;
}

export interface AskUserQuestion {
  question: string;
  header: string;
  options: AskUserOption[];
  multi_select: boolean;
}

export interface AskUserRequest {
  request_id: string;
  questions: AskUserQuestion[];
}

// Plan approval types
export interface PlanApprovalRequest {
  request_id: string;
  plan_content: string;
}

// ── Project workspace types ─────────────────────────────────────────────────

export interface Project {
  id: string;
  name: string;
  workspace_path: string;
  created_at: string | null;
  conversation_count: number;
}

export interface Conversation {
  id: string;
  name: string;
  project_id: string;
  working_directory: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface Artifact {
  id: number;
  project_id: number | null;
  conversation_id: number | null;
  type: 'file' | 'code' | 'report' | 'image' | 'data';
  source_mode: string | null;
  title: string | null;
  pinned: boolean;
  payload_ref: string | null;
  preview: any | null;
  size?: number; // Actual file size in bytes
  created_at: string;
  updated_at: string | null;
}

// Per-session state for concurrent session support
export interface PerSessionState {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  pendingApproval: ApprovalRequest | null;
  pendingAskUser: AskUserRequest | null;
  pendingPlanApproval: PlanApprovalRequest | null;
  progressMessage: string | null;
  queuedMessages: string[];
  selectedPersona?: string | null;
  // Unsent input text, kept per-conversation so it survives navigating away
  // (e.g. opening a module dashboard) and back.
  draft?: string;
}

// ── Artifact Viewer ──────────────────────────────────────────────────────────
export interface FsEntry {
  name: string;
  kind: 'file' | 'dir';
  size: number;
  mtime: number;
  ext: string;
}

export interface FsListResponse {
  path: string;
  entries: FsEntry[];
}

// A location to reveal/highlight when a viewer tab opens. `text` is the most
// robust anchor (searched in the opened file, immune to CRLF/front-matter
// offset drift); `start`/`end`/`line` are used when offsets are exact. `nonce`
// changes on every request so re-clicking the same citation re-triggers the
// reveal.
export interface ViewerLocation {
  start?: number;
  end?: number;
  line?: number;
  text?: string;
  nonce?: number;
}

export type ViewerTab =
  | {
      kind: 'file';
      id: string;       // === path
      path: string;     // relative to working_directory
      name: string;
      ext: string;
      location?: ViewerLocation;
    }
  | {
      kind: 'module';
      id: string;       // === `module:<name>`
      name: string;     // module name
    }
  | {
      kind: 'module-file';
      id: string;       // === `module:<module>:<path>`
      module: string;
      path: string;     // relative to module folder
      name: string;
      ext: string;
      location?: ViewerLocation;
    };

// File-tree / fs-API scope. Either a conversation working directory or a module folder.
export type FsScope =
  | { kind: 'conv'; id: number }
  | { kind: 'module'; name: string };

export function fsScopeKey(scope: FsScope): string {
  return scope.kind === 'conv' ? `conv:${scope.id}` : `module:${scope.name}`;
}

export interface Persona {
  name: string;
  system_prompt: string;
  is_built_in: boolean;
  created_at: string;
}

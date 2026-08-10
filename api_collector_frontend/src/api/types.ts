/**
 * TypeScript interfaces for all API responses.
 * 
 * Ensures type safety across all frontend API calls.
 */

// Backend readiness
export interface BackendReadyResponse {
  backend: "ready" | "unavailable";
  validator: "ready" | "unavailable";
  orchestrator: "ready" | "unavailable";
  generator: "ready" | "unavailable";
  env: {
    google_api_key: boolean;
    openai_api_key: boolean;
  };
}

// Tool collection
export interface Tool {
  name: string;
  description: string;
  method?: string;
  path?: string;
  tags: string[];
  parameters: any[];
  metadata: Record<string, any>;
}

export interface CollectToolsResponse {
  tools: Tool[];
  source_type?: string;
  csv_content?: string;
}

// Validation
export interface ValidationIssue {
  severity: "critical" | "warning" | "suggestion";
  category: string;
  line?: number;
  description: string;
  suggestion?: string;
  snippet?: string;
  cwe?: string;
  rule_id?: string;
}

export interface ValidationResponse {
  approved: boolean;
  quality_score: number;
  iteration: number;
  errors: string[];
  warnings: string[];
  suggestions: string[];
  total_issues?: number;
  llm_validation?: {
    score?: number;
    summary?: string;
    reasoning?: string;
    improvements?: string[];
    patterns_detected?: string[];
    risk_assessment?: string;
    quality_breakdown?: Record<string, number>;
  };
  risk_assessment?: string;
  reasoning?: string;
}

// Code generation
export interface GenerationResponse {
  code: string;
  iteration: number;
  context_id?: string;
  metadata?: Record<string, any>;
}

// Orchestrator status
export interface OrchestratorStatus {
  status: string;
  current_state?: string;
  pipeline_id?: string;
  iteration?: number;
  agents?: {
    generator?: "ready" | "unavailable";
    validator?: "ready" | "unavailable";
    ui_controller?: "ready" | "unavailable";
  };
}

// Pipeline state
export interface PipelineStateResponse {
  state: string;
  context_id?: string;
  iteration?: number;
  tools_count?: number;
  code_generated?: boolean;
  validation_passed?: boolean;
}

// Error responses
export interface ErrorResponse {
  detail: string;
  error?: string;
  status_code?: number;
}


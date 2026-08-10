// Edited by Dr. Wasim
import React, { useState, useEffect, useRef } from 'react';
import StatusHeader from './components/StatusHeader';
import { PipelineFlow } from './components/PipelineFlow';
import { ActivityLog, ActivityLogEntry } from './components/ActivityLog';
import TimerDisplay from './components/TimerDisplay';
import CodePanel from './components/CodePanel';
import { ValidationFeedback } from './components/ValidationFeedback';
import ChatPanel from './components/ChatPanel';
import IterationTabs from './components/IterationTabs';
import A2ACommunicationLog from './components/A2ACommunicationLog';
import MongoMCPServers from './components/MongoMCPServers';
import DBMCPGenerator from './components/DBMCPGenerator';
import { ConnectionStatus as ConnectionStatusComponent, ConnectionStatus as ConnectionStatusType } from './components/ConnectionStatus';
import { BackendBanner } from './components/BackendBanner';
import { useWebSocket } from './hooks/useWebSocket';
import { waitForBackendReady, checkBackendConnection } from './api/backend';
import './App.css';

// Type definitions
export type SourceType = 'file' | 'url' | 'sdk';
export type PipelineState =
  | 'initial'
  | 'input_received'
  | 'collecting_tools'
  | 'tools_ready'
  | 'generating_code'
  | 'awaiting_validation'
  | 'validating_code'
  | 'validation_result'
  | 'awaiting_regen'
  | 'regenerating_code'
  | 'done'
  | 'failed_final';

export interface Tool {
  name: string;
  description: string;
  method?: string;
  path?: string;
  tags: string[];
  parameters: any[];
  metadata: Record<string, any>;
}

export interface ValidationResult {
  approved: boolean;
  quality_score: number;
  iteration: number;
  errors: any[];
  warnings: any[];
  metadata?: {
    score_weights?: Record<string, number>;
    category_deductions?: Record<string, number>;
  };
  llm_validation?: {
    reasoning?: string;
    quality_breakdown?: Record<string, number>;
    risk_assessment?: string;
    improvements?: string[];
  };
  feedback?: string;
}

interface CodeIteration {
  iteration: number;
  code: string;
  timestamp: Date;
  validationResult?: ValidationResult;
}

export interface TelemetryEvent {
  event_id: string;
  correlation_id: string;
  context_id?: string;
  from_agent: string;
  to_agent: string;
  request_payload: Record<string, any>;
  response_payload: Record<string, any> | null;
  send_ts: number;
  recv_ts: number;
  latency_ms: number;
  status?: string;
}

function App() {
  // Backend connection state
  const [backendReady, setBackendReady] = useState<boolean>(false);
  const [backendBannerVisible, setBackendBannerVisible] = useState<boolean>(false);
  const [serviceStatuses, setServiceStatuses] = useState<{
    orchestrator: ConnectionStatusType;
    generator: ConnectionStatusType;
    validator: ConnectionStatusType;
    backend: ConnectionStatusType;
  }>({
    orchestrator: "connecting",
    generator: "connecting",
    validator: "connecting",
    backend: "connecting",
  });
  const backendCheckAttemptsRef = useRef<number>(0);
  const maxBackendAttempts = 20;
  
  // State
  const [contextId, setContextId] = useState<string | null>(null);
  const [pipelineState, setPipelineState] = useState<PipelineState>('initial');
  const [sourceType, setSourceType] = useState<SourceType>('url');
  const [sourceData, setSourceData] = useState<string>('https://jsonplaceholder.typicode.com/');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sdkName, setSdkName] = useState<string>('');
  const [isLoading, setIsLoading] = useState(false);
  const [tools, setTools] = useState<Tool[]>([]);
  const [toolsFileName, setToolsFileName] = useState<string | null>(null);
  const [generatedCode, setGeneratedCode] = useState<string | null>(null);
  const [codeIterations, setCodeIterations] = useState<CodeIteration[]>([]);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [iteration, setIteration] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [selectedIteration, setSelectedIteration] = useState<number | null>(null);
  const [drafts, setDrafts] = useState<any[]>([]);

  // Refs
  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastCodeLengthRef = useRef<number>(0);

  // Auto Run state
  const [isAutoRunning, setIsAutoRunning] = useState(false);
  const [autoRunTotalIterations, setAutoRunTotalIterations] = useState(0);
  const [autoRunBatchIterations, setAutoRunBatchIterations] = useState(0);
  const [autoRunStatus, setAutoRunStatus] = useState<string>('');
  const autoRunAbortRef = useRef(false);
  const isAutoRunningRef = useRef(false); // Ref to track auto-run state for async callbacks
  const contextIdRef = useRef<string | null>(null); // Ref to track context ID for async callbacks
  
  // Auto Run Constants
  const AUTO_RUN_BATCH_LIMIT = 5; // Max iterations per batch (per click)
  const AUTO_RUN_MAX_ITERATIONS = 10; // Max total iterations across all batches
  const AUTO_RUN_SUCCESS_THRESHOLD = 80; // Score threshold for success (80%)

  // Activity log state
  const [activities, setActivities] = useState<ActivityLogEntry[]>([]);
  const [telemetryEvents, setTelemetryEvents] = useState<TelemetryEvent[]>([]);

  // Helper to add activity
  const addActivity = (type: 'info' | 'success' | 'warning' | 'error', agent: string, message: string) => {
    const newActivity: ActivityLogEntry = {
      id: `${Date.now()}-${Math.random()}`,
      timestamp: new Date(),
      type,
      agent,
      message
    };
    setActivities((prev: ActivityLogEntry[]) => [...prev, newActivity]);
  };

  // Timer state
  const [activeTimer, setActiveTimer] = useState<{
    action: 'validate' | 'regenerate';
    remaining: number;
    total: number;
  } | null>(null);

  // Backend startup logic
  useEffect(() => {
    let mounted = true;
    let retryInterval: ReturnType<typeof setInterval> | null = null;

    const initializeBackend = async () => {
      // Try to wait for backend with retries
      const result = await waitForBackendReady(
        undefined, // Use default URL
        500, // 500ms interval
        maxBackendAttempts,
        (attempt, maxAttempts) => {
          if (mounted) {
            backendCheckAttemptsRef.current = attempt;
            if (attempt >= maxAttempts) {
              setBackendBannerVisible(true);
            }
          }
        }
      );

      if (!mounted) return;

      if (result && result.backend === "ready") {
        setBackendReady(true);
        setBackendBannerVisible(false);
        backendCheckAttemptsRef.current = 0;
        
        // Fire global event
        window.dispatchEvent(new CustomEvent("backend-connected", {
          detail: result,
        }));
      } else {
        setBackendReady(false);
        setBackendBannerVisible(true);
        
        // Set up automatic recovery - retry every 2 seconds
        retryInterval = setInterval(async () => {
          if (!mounted) return;
          
          const isConnected = await checkBackendConnection();
          if (isConnected) {
            setBackendReady(true);
            setBackendBannerVisible(false);
            backendCheckAttemptsRef.current = 0;
            
            if (retryInterval) {
              clearInterval(retryInterval);
              retryInterval = null;
            }
            
            // Fire global event
            window.dispatchEvent(new CustomEvent("backend-connected"));
          }
        }, 2000);
      }
    };

    initializeBackend();

    // Listen for connection loss events
    const handleConnectionLost = () => {
      if (mounted) {
        setBackendReady(false);
        setBackendBannerVisible(true);
      }
    };

    window.addEventListener("backend-connection-lost", handleConnectionLost);

    return () => {
      mounted = false;
      if (retryInterval) {
        clearInterval(retryInterval);
      }
      window.removeEventListener("backend-connection-lost", handleConnectionLost);
    };
  }, []);

  // WebSocket connection
  const { connected, sendMessage } = useWebSocket({
    url: 'ws://127.0.0.1:8102/ws',
    onMessage: handleWebSocketMessage,
    reconnectInterval: 2000,
    maxReconnectAttempts: 10
  });


  // Handle WebSocket messages
  function handleWebSocketMessage(data: any) {
    console.log('WebSocket message:', data);

    switch (data.type) {
      case 'connected':
        addActivity('success', 'System', 'Connected to UI Controller - WebSocket active');
        break;

      case 'state_change':
        const toState = data.data.to_state;
        setPipelineState(toState);

                const stateMessages: Record<string, string> = {
          'input_received': 'Input received - Starting pipeline',
          'collecting_tools': 'Extracting API tools from source',
          'tools_ready': 'Tools extracted successfully',
          'generating_code': 'AI is generating MCP server code',
          'awaiting_validation': 'Code generated - Ready for validation',
          'validating_code': 'AI is validating code quality',
          'validation_result': 'Validation complete',
          'awaiting_regen': 'Ready for regeneration',
          'regenerating_code': 'Regenerating code with improvements',
          'done': 'Pipeline complete - MCP server ready!',
          'failed_final': 'Pipeline failed after maximum attempts'
        };

        if (stateMessages[toState]) {
          const activityType = toState === 'done' ? 'success' : toState === 'failed_final' ? 'error' : 'info';
          addActivity(activityType, 'Orchestrator', stateMessages[toState]);
        }

        // AUTO-TRIGGER VALIDATION: If Auto Run is active and state changed to awaiting_validation
        if (toState === 'awaiting_validation' && isAutoRunningRef.current && contextIdRef.current) {
          console.log('🔍 Auto Run active: Auto-triggering validation from WebSocket state change...');
          addActivity('info', 'AutoRun', '🔍 Auto-triggering validation (from WebSocket)...');
          sendMessage({
            type: 'validate_manual',
            context_id: contextIdRef.current
          });
        }
        break;

      case 'timer_start':
        setActiveTimer({
          action: data.data.action,
          remaining: data.data.duration,
          total: data.data.duration
        });
        const timerAction = data.data.action === 'validate' ? 'validation' : 'regeneration';
        addActivity('info', 'System', `Auto-${timerAction} timer started (${data.data.duration}s)`);
        break;

      case 'timer_tick':
        setActiveTimer({
          action: data.data.action,
          remaining: data.data.remaining,
          total: data.data.total
        });
        break;

      case 'timer_cancel':
        setActiveTimer(null);
        addActivity('warning', 'System', 'Timer cancelled by user');
        break;

      case 'tools_updated':
        const toolCount = data.data.count || 0;
        if (toolCount > 0 && pipelineState === 'collecting_tools') {
          setPipelineState('tools_ready');
        }
        if (toolCount > 0) {
          setError(null);
        }
        addActivity('success', 'Backend', `Extracted ${toolCount} API tools`);
        break;

      case 'code_generated':
        const newIteration = data.data.iteration || iteration + 1;
        setIteration(newIteration);
        const currentCodeLength = data.data.code_length;
        if (currentCodeLength !== lastCodeLengthRef.current) {
          addActivity('success', 'Generator', `Code generated (Attempt ${newIteration}, ${currentCodeLength} chars)`);
          lastCodeLengthRef.current = currentCodeLength;
        }
        if (contextId) {
          fetchCode(contextId, newIteration);
        }
        break;

      case 'validation_result':
        const validationData = data.data;
        setValidationResult(validationData);
        const approved = validationData.approved;
        const score = validationData.quality_score;
        
        // Store validation result with current iteration
        setCodeIterations((prev: CodeIteration[]) => {
          const currentIter = iteration || prev.length;
          return prev.map((ci: CodeIteration) => 
            ci.iteration === currentIter 
              ? { ...ci, validationResult: validationData }
              : ci
          );
        });
        
        if (approved) {
          addActivity('success', 'Validator', `Code approved! Quality score: ${score}/100`);
        } else {
          addActivity('warning', 'Validator', `Code rejected. Quality score: ${score}/100`);
        }
        break;

      case 'error':
        const errorMsg = data.error || data.message || data.data?.error || data.data?.message || 'Unknown error occurred';
        const isFatal = data.data?.fatal || false;
        const actionRequired = data.data?.action_required || '';
        const shouldReset = data.reset_pipeline || data.data?.reset_pipeline || false;
        const isNoEndpointsError = errorMsg.toLowerCase().includes('no api endpoints could be extracted');

        // If tools are already loaded, suppress the "no endpoints" error and keep state consistent.
        if (isNoEndpointsError && tools.length > 0) {
          addActivity('warning', 'System', 'Ignoring no-endpoints error because tools are already loaded.');
          return;
        }
        
        // Check if it's an API key/quota error
        const isApiError = errorMsg.toLowerCase().includes('api key') || 
                          errorMsg.toLowerCase().includes('quota') || 
                          errorMsg.toLowerCase().includes('429') ||
                          errorMsg.toLowerCase().includes('401') ||
                          errorMsg.toLowerCase().includes('403');
        
        setError(errorMsg);
        addActivity('error', 'System', `${errorMsg}`);
        
        // Show prominent error message (Toast/Alert) for all errors, especially input validation errors
        const isInputError = errorMsg.toLowerCase().includes('invalid input') || 
                            errorMsg.toLowerCase().includes('please provide a valid');
        
        if (isInputError || isApiError || isFatal) {
          // Use alert for now (can be replaced with a Toast library later)
          alert(`Error: ${errorMsg}${actionRequired ? '\n\n' + actionRequired : ''}`);
        }
        
        // Reset pipeline state if requested
        if (shouldReset) {
          // Reset pipeline state to allow user to try again
          setPipelineState('initial');
          setIsAutoRunning(false);
          isAutoRunningRef.current = false;
          autoRunAbortRef.current = false;
          setAutoRunStatus('');
          setContextId(null);
          contextIdRef.current = null;
          setIteration(0);
          setGeneratedCode(null);
          setValidationResult(null);
          setCodeIterations([]);
          addActivity('info', 'System', 'Pipeline state reset. You can try again.');
        }
        break;

      case 'telemetry':
        // ONLY display real backend telemetry events
        // NO UI-generated, NO inferred, NO simulated logs
        if (data.event && 
            data.event.request_payload && 
            data.event.response_payload &&
            data.event.from_agent &&
            data.event.to_agent &&
            data.event.send_ts &&
            data.event.event_id) {
          setTelemetryEvents((prev: TelemetryEvent[]) => {
            // Deduplicate by event_id (backend source of truth)
            if (prev.some((p) => p.event_id === data.event.event_id)) {
              return prev;
            }
            // Add event (backend telemetry only)
            const next = [...prev, data.event];
            return next.sort((a, b) => (a.send_ts || 0) - (b.send_ts || 0));
          });
        } else {
          console.warn('Invalid telemetry event (missing required fields):', data.event);
        }
        break;

      case 'telemetry_replay':
        // Replay buffered telemetry events (backend source of truth)
        if (Array.isArray(data.events)) {
          setTelemetryEvents((prev: TelemetryEvent[]) => {
            const existingIds = new Set(prev.map((p) => p.event_id));
            // Only accept complete backend telemetry events
            const incoming = data.events.filter(
              (ev: any) =>
                ev &&
                ev.request_payload &&
                ev.response_payload &&
                ev.from_agent &&
                ev.to_agent &&
                ev.send_ts &&
                ev.event_id &&
                !existingIds.has(ev.event_id)
            );
            if (incoming.length === 0) {
              return prev;
            }
            // Add replayed events (backend telemetry only)
            const next = [...prev, ...incoming];
            return next.sort((a, b) => (a.send_ts || 0) - (b.send_ts || 0));
          });
        }
        break;
    }
  }

  // Generate draft using System A
  const handleGenerateDraft = async () => {
    if (!contextId) {
      addActivity('error', 'System', 'No context available. Start pipeline first.');
      return;
    }
    if (tools.length === 0) {
      addActivity('error', 'System', 'Load tools before generating a draft.');
      return;
    }
    try {
      setIsLoading(true);
      const response = await fetch('/api/draft/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          context_id: contextId,
          prompt: 'Generate MCP draft',
          tools: tools.map((t: Tool) => ({
            ...t,
            base_url: (t as any).base_url || (t as any).metadata?.base_url,
          })),
        }),
      });
      if (!response.ok) {
        throw new Error('Draft generation failed');
      }
      const data = await response.json();
      setDrafts((prev) => [...prev, data]);
      addActivity('success', 'System A', `Draft generated (draft_id=${data.draft_id.slice(0, 8)}...)`);
    } catch (err: any) {
      addActivity('error', 'System A', err.message || 'Draft generation failed');
    } finally {
      setIsLoading(false);
    }
  };

  // Send draft to validator pipeline
  const handleSubmitDraft = async (draft: any) => {
    try {
      setIsLoading(true);
      const response = await fetch('http://127.0.0.1:8100/draft/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(draft),
      });
      if (!response.ok) throw new Error('Failed to submit draft');
      const data = await response.json();
      addActivity('info', 'Orchestrator', `Draft submitted for validation (draft_id=${data.draft_id.slice(0, 8)}...)`);
    } catch (err: any) {
      addActivity('error', 'System', err.message || 'Failed to submit draft');
    } finally {
      setIsLoading(false);
    }
  };

  // Handle file selection
  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setSourceType('file');
      setSourceData('');
      setSdkName('');
      addActivity('info', 'System', ` File selected: ${file.name}`);
    }
  };

  // FORGE TOOLS - Extract tools from source
  const handleForgeTools = async () => {
    if (!selectedFile && !sourceData && !sdkName) {
      setError('Please select a file, enter a URL, or specify a Python SDK name');
      return;
    }

    try {
      setIsLoading(true);
      setError(null);
      setTools([]);
      setToolsFileName(null);
      setPipelineState('collecting_tools');
      addActivity('info', 'System', ' Forging tools from source...');

      const formData = new FormData();
      
      // Only append the relevant field based on source type
      // Note: Don't send source_type when uploading file - let parsers auto-detect based on file content
      if (selectedFile && sourceType === 'file') {
        formData.append('file', selectedFile);
        // Explicitly DO NOT send source_type - backend will auto-detect (OpenAPI if has "paths", Postman if has "info"+"item")
        // Don't append url or sdk_name when using file
      } else if (sourceData && sourceData.trim() && sourceType === 'url') {
        formData.append('url', sourceData.trim());
        formData.append('source_type', 'url');
        // Don't append file or sdk_name when using url
      } else if (sdkName && sdkName.trim() && sourceType === 'sdk') {
        formData.append('sdk_name', sdkName.trim());
        formData.append('source_type', 'sdk');
        // Don't append file or url when using sdk
      } else {
        throw new Error('Invalid source configuration');
      }

      formData.append('output_format', 'json');

      const response = await fetch('http://127.0.0.1:8000/collect-tools', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${response.statusText} - ${errorText}`);
      }

      const data = await response.json();
      const fetchedTools: Tool[] = data.tools || [];

      setTools(fetchedTools);
      setToolsFileName(selectedFile?.name || sourceData || sdkName);
      setPipelineState('tools_ready');
      if (fetchedTools.length > 0) {
        setError(null);
      }
      addActivity('success', 'Backend', `? Forged ${fetchedTools.length} tools from ${sourceType}`);
      
      // Keep scroll position at top after forging tools
      setTimeout(() => {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }, 100);

    } catch (err: any) {
      setError(err.message);
      setPipelineState('initial');
      addActivity('error', 'System', `Failed to forge tools: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  // Safety: if tools are loaded, ensure pipeline state and error banner are consistent.
  useEffect(() => {
    if (tools.length > 0) {
      if (pipelineState === 'collecting_tools') {
        setPipelineState('tools_ready');
      }
      if (error && error.toLowerCase().includes('no api endpoints could be extracted')) {
        setError(null);
      }
    }
  }, [tools.length, pipelineState, error]);

  // Export tools to JSON
  const handleExportJSON = () => {
    if (tools.length === 0) return;
    
    const jsonStr = JSON.stringify(tools, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'tools.json';
    a.click();
    URL.revokeObjectURL(url);
    addActivity('success', 'System', ' Exported tools to JSON');
  };

  // Export tools to CSV
  const handleExportCSV = async () => {
    if (tools.length === 0) return;

    try {
      const formData = new FormData();
      
      // Only append the relevant field based on source type
      if (selectedFile && sourceType === 'file') {
        formData.append('file', selectedFile);
      } else if (sourceData && sourceData.trim() && sourceType === 'url') {
        formData.append('url', sourceData.trim());
      } else if (sdkName && sdkName.trim() && sourceType === 'sdk') {
        formData.append('sdk_name', sdkName.trim());
      }
      
      formData.append('output_format', 'csv');

      const response = await fetch('http://127.0.0.1:8000/collect-tools/download', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        throw new Error('Failed to export CSV');
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'tools.csv';
      a.click();
      URL.revokeObjectURL(url);
      addActivity('success', 'System', ' Exported tools to CSV');
    } catch (err: any) {
      setError(err.message);
      addActivity('error', 'System', `Failed to export CSV: ${err.message}`);
    }
  };

  // Start pipeline
  const handleStartPipeline = async () => {
    try {
      setError(null);
      addActivity('info', 'System', ' Starting pipeline...');

      if (tools.length === 0) {
        const hasSourceData = Boolean(sourceData && sourceData.trim());
        if (!hasSourceData) {
          throw new Error('No tools loaded. Please provide a URL/SDK or forge tools first.');
        }
      }

      // Sanitize tools (if any)
      const sanitizedTools: Tool[] = tools.map((t: Tool) => ({
        ...t,
        tags: Array.isArray(t.tags) ? t.tags : [],
        parameters: Array.isArray(t.parameters) ? t.parameters : [],
        metadata: (t.metadata && typeof t.metadata === 'object' && !Array.isArray(t.metadata)) ? t.metadata : {},
      }));

      // Call orchestrator to start pipeline
      const payload: Record<string, any> = {
        source_type: sourceType,
        source_data: sourceData,
      };
      if (sanitizedTools.length > 0) {
        payload.tools = sanitizedTools;
      }
      const response = await fetch('http://127.0.0.1:8100/pipeline/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error('Failed to start pipeline');
      }

      const data = await response.json();
      setContextId(data.context_id);
      contextIdRef.current = data.context_id; // Update ref for async callbacks
      addActivity('success', 'Orchestrator', `Pipeline started (Context: ${data.context_id.slice(0, 8)}...)`);

      // Start polling for status
      startStatusPolling(data.context_id);

    } catch (err: any) {
      setError(err.message);
      addActivity('error', 'System', `Failed to start pipeline: ${err.message}`);
    }
  };

  // Manual validation trigger
  const handleManualValidate = () => {
    if (!contextId) return;

    addActivity('info', 'System', ' User triggered manual validation');
    sendMessage({
      type: 'validate_manual',
      context_id: contextId
    });

    setActiveTimer(null);
  };

  // Manual regeneration trigger
  const handleManualRegenerate = () => {
    if (!contextId) return;

    addActivity('info', 'System', ' User triggered manual regeneration');
    sendMessage({
      type: 'regenerate_manual',
      context_id: contextId
    });

    setActiveTimer(null);
  };

  // Cancel timer
  const handleCancelTimer = () => {
    if (!contextId || !activeTimer) return;

    sendMessage({
      type: 'cancel_timer',
      context_id: contextId,
      action: activeTimer.action
    });

    setActiveTimer(null);
  };

  // Poll pipeline status
  const startStatusPolling = (ctxId: string) => {
    // Clear any existing polling
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }
    if (pollingTimeoutRef.current) {
      clearTimeout(pollingTimeoutRef.current);
    }

    console.log(' Starting status polling for context:', ctxId);

    pollingIntervalRef.current = setInterval(async () => {
      try {
        const response = await fetch(`http://127.0.0.1:8100/pipeline/${ctxId}/status`);
        if (response.ok) {
          const status = await response.json();
          setPipelineState(status.state);
          setIteration(status.iteration);

          // Update code if available
          if (status.has_code) {
            fetchCode(ctxId, status.iteration);
          }

          // AUTO-TRIGGER VALIDATION: If Auto Run is active and state is awaiting_validation
          if (status.state === 'awaiting_validation' && isAutoRunningRef.current) {
            console.log('🔍 Auto Run active: Auto-triggering validation from polling...');
            addActivity('info', 'AutoRun', '🔍 Auto-triggering validation (from polling)...');
            sendMessage({
              type: 'validate_manual',
              context_id: ctxId
            });
          }

          // Stop polling if done or failed
          if (status.state === 'done' || status.state === 'failed_final') {
            console.log('? Polling stopped - pipeline completed');
            if (pollingIntervalRef.current) {
              clearInterval(pollingIntervalRef.current);
              pollingIntervalRef.current = null;
            }
          }
        }
      } catch (err) {
        console.error('? Status polling error:', err);
      }
    }, 2000);

    // Clean up after 5 minutes
    pollingTimeoutRef.current = setTimeout(() => {
      console.log('? Polling timeout - stopping after 5 minutes');
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    }, 300000);
  };

  // Fetch generated code
  const fetchCode = async (ctxId: string, iter?: number) => {
    try {
      const response = await fetch(`http://127.0.0.1:8100/pipeline/${ctxId}/code`);
      if (!response.ok) {
        return;
      }
      const data = await response.json();
      if (data?.code) {
        const codeLength = data.code.length;
        const currentIter = iter || data.iteration || iteration;
        
        // Store this iteration's code
        setCodeIterations((prev: CodeIteration[]) => {
          const existing = prev.find((ci: CodeIteration) => ci.iteration === currentIter);
          if (existing) {
            return prev.map((ci: CodeIteration) => 
              ci.iteration === currentIter 
                ? { ...ci, code: data.code, timestamp: new Date() }
                : ci
            );
          }
          return [...prev, { iteration: currentIter, code: data.code, timestamp: new Date() }].sort((a: CodeIteration, b: CodeIteration) => a.iteration - b.iteration);
        });
        
        if (codeLength !== lastCodeLengthRef.current) {
          lastCodeLengthRef.current = codeLength;
          setGeneratedCode(data.code);
          setSelectedIteration(currentIter);
          addActivity('success', 'Orchestrator', `? Code received (Iteration ${currentIter}, ${codeLength} chars)`);
        }
      }
    } catch (err) {
      console.error('Error fetching code:', err);
    }
  };

  // ==================== AUTO RUN HANDLERS ====================
  
  /**
   * Auto Run Pipeline
   * Runs the full pipeline: Forge Tools → Start Pipeline → iterate until done
   * - Runs up to AUTO_RUN_BATCH_LIMIT (5) iterations per click
   * - Stops when score >= AUTO_RUN_SUCCESS_THRESHOLD (80%)
   * - Max total iterations: AUTO_RUN_MAX_ITERATIONS (10)
   */
  const handleAutoRun = async () => {
    // Reset abort flag
    autoRunAbortRef.current = false;
    setIsAutoRunning(true);
    isAutoRunningRef.current = true; // Update ref for async callbacks
    setError(null);
    setAutoRunBatchIterations(0);

    // Check if we've reached max total iterations
    if (autoRunTotalIterations >= AUTO_RUN_MAX_ITERATIONS) {
      setAutoRunStatus("Max iterations (10) reached. Click Reset to start over.");
      setIsAutoRunning(false);
      return;
    }

    addActivity('info', 'AutoRun', `▶ Auto Run started (Batch ${Math.floor(autoRunTotalIterations / AUTO_RUN_BATCH_LIMIT) + 1})`);

    try {
      // Use local variable to track tools (since React state is async)
      let currentTools = tools;
      let currentContextId = contextId;

      // Step 1: Forge Tools if not already loaded
      if (currentTools.length === 0) {
        setAutoRunStatus("Step 1: Forging tools...");
        addActivity('info', 'AutoRun', '🔧 Forging tools from source...');
        
        // Call forge tools and get the result directly
        currentTools = await handleForgeToolsForAutoRun();
        
        if (autoRunAbortRef.current) {
          setIsAutoRunning(false);
          setAutoRunStatus("Auto Run stopped by user.");
          return;
        }
        
        if (currentTools.length === 0) {
          throw new Error('No tools were forged. Please check your source.');
        }
        
        addActivity('success', 'AutoRun', `🔧 Forged ${currentTools.length} tools`);
      }

      // Step 2: Start Pipeline if not already started
      if (!currentContextId && currentTools.length > 0) {
        setAutoRunStatus("Step 2: Starting pipeline...");
        addActivity('info', 'AutoRun', '🚀 Starting pipeline...');
        
        // Start pipeline with the tools we have
        currentContextId = await handleStartPipelineForAutoRun(currentTools);
        
        if (autoRunAbortRef.current) {
          setIsAutoRunning(false);
          setAutoRunStatus("Auto Run stopped by user.");
          return;
        }
        
        addActivity('success', 'AutoRun', `🚀 Pipeline started (Context: ${currentContextId.slice(0, 8)}...)`);
      }

      // Step 3: Monitor pipeline and iterate
      let currentBatchIteration = 0;
      let currentTotalIteration = autoRunTotalIterations;
      
      // Increment iteration counter for the first run
      currentTotalIteration++;
      setAutoRunTotalIterations(currentTotalIteration);
      
      while (
        currentBatchIteration < AUTO_RUN_BATCH_LIMIT &&
        currentTotalIteration <= AUTO_RUN_MAX_ITERATIONS &&
        !autoRunAbortRef.current
      ) {
        // Wait for pipeline state changes
        setAutoRunStatus(`Iteration ${currentTotalIteration}/${AUTO_RUN_MAX_ITERATIONS}: Monitoring pipeline...`);
        
        // Poll for status
        await new Promise(resolve => setTimeout(resolve, 3000));
        
        // Fetch current pipeline status
        if (currentContextId) {
          try {
            const statusResponse = await fetch(`http://127.0.0.1:8100/pipeline/${currentContextId}/status`);
            if (statusResponse.ok) {
              const status = await statusResponse.json();
              setPipelineState(status.state);
              setIteration(status.iteration);
              
              // Check if pipeline is done
              if (status.state === 'done') {
                const finalScore = status.quality_score || validationResult?.quality_score || 0;
                setAutoRunStatus(`✅ Pipeline complete! Final score: ${finalScore}%`);
                addActivity('success', 'AutoRun', `✅ Pipeline complete! Final score: ${finalScore}%`);
                setIsAutoRunning(false);
                isAutoRunningRef.current = false;
                return;
              }
              
              // Check if pipeline failed
              if (status.state === 'failed_final') {
                setAutoRunStatus(`❌ Pipeline failed after maximum attempts.`);
                addActivity('error', 'AutoRun', '❌ Pipeline failed');
                setIsAutoRunning(false);
                isAutoRunningRef.current = false;
                return;
              }
              
              // AUTO-TRIGGER VALIDATION when awaiting_validation
              if (status.state === 'awaiting_validation') {
                setAutoRunStatus(`Iteration ${currentTotalIteration}/${AUTO_RUN_MAX_ITERATIONS}: Auto-triggering validation...`);
                addActivity('info', 'AutoRun', '🔍 Auto-triggering validation...');
                
                // Trigger validation via WebSocket
                sendMessage({
                  type: 'validate_manual',
                  context_id: currentContextId
                });
                
                // Wait for validation to start processing
                await new Promise(resolve => setTimeout(resolve, 2000));
                continue; // Continue loop to check for validation result
              }
              
              // Check validation result
              if (status.state === 'validation_result' || status.state === 'awaiting_regen') {
                const score = status.quality_score || validationResult?.quality_score || 0;
                
                if (score >= AUTO_RUN_SUCCESS_THRESHOLD) {
                  setAutoRunStatus(`✅ Success! Score: ${score}% (threshold: ${AUTO_RUN_SUCCESS_THRESHOLD}%)`);
                  addActivity('success', 'AutoRun', `✅ Auto Run complete! Score: ${score}%`);
                  setIsAutoRunning(false);
                  isAutoRunningRef.current = false;
                  return;
                }
                
                // Need to regenerate
                if (currentBatchIteration < AUTO_RUN_BATCH_LIMIT - 1 && currentTotalIteration < AUTO_RUN_MAX_ITERATIONS) {
                  currentBatchIteration++;
                  currentTotalIteration++;
                  setAutoRunBatchIterations(currentBatchIteration);
                  setAutoRunTotalIterations(currentTotalIteration);
                  
                  setAutoRunStatus(`Iteration ${currentTotalIteration}/${AUTO_RUN_MAX_ITERATIONS}: Regenerating (Score: ${score}%)...`);
                  addActivity('info', 'AutoRun', `🔄 Regenerating code (Iteration ${currentTotalIteration}, Score: ${score}%)`);
                  
                  // Trigger regeneration via WebSocket
                  sendMessage({
                    type: 'regenerate_manual',
                    context_id: currentContextId
                  });
                  
                  // Wait for regeneration to start
                  await new Promise(resolve => setTimeout(resolve, 2000));
                }
              }
              
              // If validating, just wait
              if (status.state === 'validating_code') {
                setAutoRunStatus(`Iteration ${currentTotalIteration}/${AUTO_RUN_MAX_ITERATIONS}: Validating code...`);
              }
              
              // If generating/regenerating, just wait
              if (status.state === 'generating_code' || status.state === 'regenerating_code') {
                setAutoRunStatus(`Iteration ${currentTotalIteration}/${AUTO_RUN_MAX_ITERATIONS}: Generating code...`);
              }
            }
          } catch (err) {
            console.error('Status polling error:', err);
          }
        }
        
        // Small delay between checks
        await new Promise(resolve => setTimeout(resolve, 2000));
      }

      // Determine final status
      if (autoRunAbortRef.current) {
        setAutoRunStatus("Auto Run stopped by user.");
        addActivity('warning', 'AutoRun', '⏹ Auto Run stopped by user');
      } else if (currentTotalIteration >= AUTO_RUN_MAX_ITERATIONS) {
        const finalScore = validationResult?.quality_score || 0;
        setAutoRunStatus(`Max iterations (${AUTO_RUN_MAX_ITERATIONS}) reached. Final score: ${finalScore}%`);
        addActivity('warning', 'AutoRun', `⚠ Max iterations reached. Final score: ${finalScore}%`);
      } else if (currentBatchIteration >= AUTO_RUN_BATCH_LIMIT) {
        const currentScore = validationResult?.quality_score || 0;
        setAutoRunStatus(`Batch complete (${currentBatchIteration + 1}/${AUTO_RUN_BATCH_LIMIT}). Click Auto Run to continue. Score: ${currentScore}%`);
        addActivity('info', 'AutoRun', `📦 Batch complete. Click Auto Run to continue.`);
      }

    } catch (err: any) {
      setError(err.message || "Auto Run failed.");
      setAutoRunStatus(`Auto Run failed: ${err.message}`);
      addActivity('error', 'AutoRun', `❌ Auto Run failed: ${err.message}`);
    } finally {
      setIsAutoRunning(false);
      isAutoRunningRef.current = false;
    }
  };

  /**
   * Forge tools for Auto Run (async version)
   * Returns the fetched tools directly (doesn't rely on state)
   */
  const handleForgeToolsForAutoRun = async (): Promise<Tool[]> => {
    if (!selectedFile && !sourceData && !sdkName) {
      throw new Error('Please select a file, enter a URL, or specify a Python SDK name');
    }

    setIsLoading(true);
    setError(null);
    setTools([]);
    setToolsFileName(null);
    setPipelineState('collecting_tools');

    const formData = new FormData();
    
    if (selectedFile && sourceType === 'file') {
      formData.append('file', selectedFile);
    } else if (sourceData && sourceData.trim() && sourceType === 'url') {
      formData.append('url', sourceData.trim());
      formData.append('source_type', 'url');
    } else if (sdkName && sdkName.trim() && sourceType === 'sdk') {
      formData.append('sdk_name', sdkName.trim());
      formData.append('source_type', 'sdk');
    } else {
      throw new Error('Invalid source configuration');
    }

    formData.append('output_format', 'json');

    const response = await fetch('http://127.0.0.1:8000/collect-tools', {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`HTTP ${response.status}: ${response.statusText} - ${errorText}`);
    }

    const data = await response.json();
    const fetchedTools: Tool[] = data.tools || [];

    // Update state
    setTools(fetchedTools);
    setToolsFileName(selectedFile?.name || sourceData || sdkName);
    setPipelineState('tools_ready');
    setIsLoading(false);
    
    // Return tools directly so caller doesn't need to wait for state
    return fetchedTools;
  };

  /**
   * Start pipeline for Auto Run (async version)
   * Takes tools as parameter (doesn't rely on state)
   * Returns the context_id
   */
  const handleStartPipelineForAutoRun = async (toolsToUse: Tool[]): Promise<string> => {
    if (toolsToUse.length === 0) {
      throw new Error('No tools loaded. Please forge tools first.');
    }

    const sanitizedTools: Tool[] = toolsToUse.map((t: Tool) => ({
      ...t,
      tags: Array.isArray(t.tags) ? t.tags : [],
      parameters: Array.isArray(t.parameters) ? t.parameters : [],
      metadata: (t.metadata && typeof t.metadata === 'object' && !Array.isArray(t.metadata)) ? t.metadata : {},
    }));

    const response = await fetch('http://127.0.0.1:8100/pipeline/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_type: sourceType,
        source_data: sourceData,
        tools: sanitizedTools
      })
    });

    if (!response.ok) {
      throw new Error('Failed to start pipeline');
    }

    const data = await response.json();
    const newContextId = data.context_id;
    
    // Update state
    setContextId(newContextId);
    contextIdRef.current = newContextId; // Update ref for async callbacks

    // Start polling for status
    startStatusPolling(newContextId);
    
    // Return context_id directly
    return newContextId;
  };

  /**
   * Stop Auto Run
   * Cancels the auto-run pipeline
   */
  const handleStopAutoRun = () => {
    autoRunAbortRef.current = true;
    isAutoRunningRef.current = false;
    setAutoRunStatus("Stopping...");
    addActivity('warning', 'AutoRun', '⏹ Stopping Auto Run...');
  };

  /**
   * Reset Auto Run
   * Resets all auto-run state to start fresh
   */
  const handleResetAutoRun = () => {
    setAutoRunTotalIterations(0);
    setAutoRunBatchIterations(0);
    setAutoRunStatus("");
    setIsAutoRunning(false);
    isAutoRunningRef.current = false;
    autoRunAbortRef.current = false;
    addActivity('info', 'AutoRun', '🔄 Auto Run reset');
  };

  // Initialize
  useEffect(() => {
    addActivity('success', 'System', '? System initialized!');
    addActivity('info', 'System', ' Select a source and click "Forge Tools" to begin');

    // Cleanup polling on unmount
    return () => {
      console.log(' Cleaning up polling intervals...');
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
      if (pollingTimeoutRef.current) {
        clearTimeout(pollingTimeoutRef.current);
      }
    };
  }, []);

  const validatorStatus: ConnectionStatusType = connected ? "connected" : serviceStatuses.validator;
  const orchestratorStatus = serviceStatuses.orchestrator;
  const generatorStatus = serviceStatuses.generator;
  const backendStatus = serviceStatuses.backend;

  return (
    <div className="app">
      {/* Backend Connection Status */}
      <ConnectionStatusComponent
        pollingInterval={2000}
        onStatusChange={(status) => {
          if (status === "connected") {
            setBackendReady(true);
            setBackendBannerVisible(false);
          } else if (status === "offline") {
            setBackendReady(false);
            setBackendBannerVisible(true);
          }
        }}
        onServiceStatusChange={(statuses) => setServiceStatuses(statuses)}
      />
      
      {/* Backend Banner */}
      <BackendBanner
        visible={backendBannerVisible}
        onDismiss={() => setBackendBannerVisible(false)}
      />
      
      {/* Status Header */}
      <StatusHeader
        orchestratorStatus={orchestratorStatus}
        validatorStatus={validatorStatus}
        generatorStatus={generatorStatus}
        backendStatus={backendStatus}
        isAutoRunning={isAutoRunning}
        autoRunStatus={autoRunStatus}
        totalIterations={autoRunTotalIterations}
        maxIterations={AUTO_RUN_MAX_ITERATIONS}
        onAutoRun={handleAutoRun}
        onStopAutoRun={handleStopAutoRun}
        onResetAutoRun={handleResetAutoRun}
        autoRunDisabled={isLoading || (!selectedFile && !sourceData && !sdkName)}
      />

      {/* Main Layout - Sidebar + Main Area */}
      <div className="app-layout">
        {/* LEFT SIDEBAR - Fixed Checklist + Activity Log */}
        <aside className="sidebar">
          <PipelineFlow
            currentState={pipelineState}
            iterationCount={iteration}
            maxIterations={5}
          />
          
          {/* Activity Log - In Sidebar */}
          <div className="sidebar-activity-log">
            <ActivityLog activities={activities} maxEntries={100} compact={true} />
          </div>
        </aside>

        {/* MAIN AREA - Execution & Results */}
        <main className="main-area">
          {/* Source Selection Section */}
          <div className="source-selection-section card">
            <h2 className="section-title">
              Upload collections, link docs, or point at a Python SDK. We'll extract MCP-ready tools you can export or chat with.
            </h2>
            
            <div className="source-tabs">
              <button
                className={`source-tab ${sourceType === 'file' ? 'active' : ''}`}
                onClick={() => {
                  setSourceType('file');
                  setSelectedFile(null);
                  setSdkName('');
                }}
              >
                <span className="tab-icon"></span>
                <span>File</span>
              </button>
              <button
                className={`source-tab ${sourceType === 'url' ? 'active' : ''}`}
                onClick={() => {
                  setSourceType('url');
                  setSelectedFile(null);
                  setSdkName('');
                  // Keep default URL if empty
                  if (!sourceData) {
                    setSourceData('https://jsonplaceholder.typicode.com/');
                  }
                }}
              >
                <span className="tab-icon"></span>
                <span>Docs URL</span>
              </button>
              <button
                className={`source-tab ${sourceType === 'sdk' ? 'active' : ''}`}
                onClick={() => {
                  setSourceType('sdk');
                  setSelectedFile(null);
                  setSourceData('');
                }}
              >
                <span className="tab-icon"></span>
                <span>Python SDK</span>
              </button>
            </div>

            {/* File Upload */}
            {sourceType === 'file' && (
              <div className="source-input-group">
                <label className="input-label">Upload File</label>
                <input
                  type="file"
                  accept=".json,.yaml,.yml,.postman_collection"
                  onChange={handleFileSelect}
                  className="file-input"
                />
                {selectedFile && (
                  <div className="file-info">
                    <span className="file-name"> {selectedFile.name}</span>
                    <span className="file-size">({(selectedFile.size / 1024).toFixed(1)} KB)</span>
                  </div>
                )}
              </div>
            )}

            {/* URL Input */}
            {sourceType === 'url' && (
              <div className="source-input-group">
                <label className="input-label">Documentation URL</label>
                <input
                  type="url"
                  className="url-input-full"
                  placeholder="https://api.example.com/docs"
                  value={sourceData}
                  onChange={(e) => setSourceData(e.target.value)}
                  disabled={isLoading}
                />
                <p className="input-hint">Backend will fetch this URL and parse OpenAPI, Postman-like docs, or crawl HTML.</p>
              </div>
            )}

            {/* Python SDK Input */}
            {sourceType === 'sdk' && (
              <div className="source-input-group">
                <label className="input-label">Python SDK Name</label>
                <input
                  type="text"
                  className="url-input-full"
                  placeholder="e.g., requests, boto3, openai"
                  value={sdkName}
                  onChange={(e) => setSdkName(e.target.value)}
                  disabled={isLoading}
                />
                <p className="input-hint">Enter the name of a Python SDK package to extract tools from.</p>
              </div>
            )}

            {/* Forge Tools Button */}
            <button
              onClick={handleForgeTools}
              className="forge-tools-button"
              disabled={isLoading || (!selectedFile && !sourceData && !sdkName)}
            >
              <span className="button-icon"></span>
              <span>{isLoading ? 'Forging...' : 'Forge tools'}</span>
            </button>
          </div>

          {/* API Tools Section - Step 2 - Only show when tools are loaded */}
          {tools.length > 0 && (
            <div className="tools-section card">
              <div className="tools-section-header">
                <div>
                  <h2 className="section-title">Step 2: Inspect & export tools</h2>
                  <p className="section-subtitle">Source: {sourceType}  Tools: {tools.length}</p>
                </div>
                <div className="export-buttons">
                  <button
                    onClick={handleExportJSON}
                    className="export-button json"
                  >
                     JSON export
                  </button>
                  <button
                    onClick={handleExportCSV}
                    className="export-button csv"
                  >
                     CSV export
                  </button>
                </div>
              </div>
              
              <div className="tools-table-container">
                <table className="tools-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Method</th>
                      <th>Path</th>
                      <th>Tags</th>
                      <th>Parameters</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tools.map((tool: Tool, idx: number) => (
                      <tr key={idx}>
                        <td>
                          <div className="tool-name-cell">
                            <strong>{tool.name}</strong>
                            <div className="tool-description">{tool.description}</div>
                          </div>
                        </td>
                        <td>
                          <span className={`method-badge ${tool.method?.toLowerCase() || 'unknown'}`}>
                            {tool.method || 'N/A'}
                          </span>
                        </td>
                        <td>{tool.path || ''}</td>
                        <td>
                          <div className="tags-cell">
                            {tool.tags?.slice(0, 3).map((tag: string, i: number) => (
                              <span key={i} className="tag">{tag}</span>
                            ))}
                            {tool.tags?.length > 3 && <span className="tag-more">+{tool.tags.length - 3}</span>}
                          </div>
                        </td>
                        <td>
                          {tool.parameters && Array.isArray(tool.parameters) 
                            ? tool.parameters.length > 0 
                              ? `${tool.parameters.length} ${tool.parameters.length === 1 ? 'param' : 'params'}` 
                              : '0 params'
                            : typeof tool.parameters === 'object' && tool.parameters !== null
                              ? Object.keys(tool.parameters).length + ' params'
                              : '0 params'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Timer Display */}
          {activeTimer && (
            <TimerDisplay
              action={activeTimer.action}
              remaining={activeTimer.remaining}
              total={activeTimer.total}
              onCancel={handleCancelTimer}
            />
          )}

          {/* Code Iterations with Tabs - Shows all iterations with validation feedback */}
          {codeIterations.length > 0 && (
            <div className="card">
              <IterationTabs
                iterations={codeIterations}
                selectedIteration={selectedIteration || iteration || codeIterations[codeIterations.length - 1]?.iteration || null}
                onSelectIteration={(iter: number) => {
                  setSelectedIteration(iter);
                  const selected = codeIterations.find((ci: CodeIteration) => ci.iteration === iter);
                  if (selected) {
                    setGeneratedCode(selected.code);
                    setValidationResult(selected.validationResult || null);
                  }
                }}
              />
            </div>
          )}

          {/* Fallback: Generated Code - Show if no iterations yet */}
          {codeIterations.length === 0 && generatedCode && (
            <div className="card">
              <CodePanel 
                code={generatedCode}
                iteration={iteration}
                issues={validationResult ? [
                  ...(validationResult.errors || []).map((e: any) => {
                    // Extract line number - prioritize line, then line_start, then lineNumber
                    // All should be 1-based (first line = 1)
                    const lineNum = (e.line !== undefined && e.line !== null) ? e.line : 
                                   (e.line_start !== undefined && e.line_start !== null) ? e.line_start : 
                                   (e.lineNumber !== undefined && e.lineNumber !== null) ? e.lineNumber : 0;
                    
                    // Log for debugging if line number seems wrong
                    if (lineNum > 0 && lineNum < 1000) {
                      console.log(`Error issue line ${lineNum}:`, { 
                        description: e.description?.substring(0, 50), 
                        code_snippet: e.code_snippet?.substring(0, 30) 
                      });
                    }
                    
                    return {
                      line: lineNum,
                      severity: 'error' as const,
                      description: e.description || e.message || ''
                    };
                  }),
                  ...(validationResult.warnings || []).map((w: any) => {
                    // Extract line number - prioritize line, then line_start, then lineNumber
                    // All should be 1-based (first line = 1)
                    const lineNum = (w.line !== undefined && w.line !== null) ? w.line : 
                                   (w.line_start !== undefined && w.line_start !== null) ? w.line_start : 
                                   (w.lineNumber !== undefined && w.lineNumber !== null) ? w.lineNumber : 0;
                    
                    // Log for debugging if line number seems wrong
                    if (lineNum > 0 && lineNum < 1000) {
                      console.log(`Warning issue line ${lineNum}:`, { 
                        description: w.description?.substring(0, 50), 
                        code_snippet: w.code_snippet?.substring(0, 30) 
                      });
                    }
                    
                    return {
                      line: lineNum,
                      severity: 'warning' as const,
                      description: w.description || w.message || ''
                    };
                  })
                ] : []}
              />
            </div>
          )}

          {/* Action Buttons - AFTER CODE SECTION */}
          <div className="actions-section card">
            <h2 className="section-title"> Actions</h2>
            <div className="action-buttons-grid">
              {pipelineState === 'initial' && (
                <button
                  onClick={handleStartPipeline}
                  className="action-btn primary"
                  disabled={isLoading}
                >
                  <span className="btn-icon"></span>
                  <span>Start Pipeline</span>
                </button>
              )}

              {pipelineState === 'tools_ready' && (
                <button
                  onClick={handleStartPipeline}
                  className="action-btn primary"
                  disabled={isLoading}
                >
                  <span className="btn-icon"></span>
                  <span>Start Pipeline</span>
                </button>
              )}

              {pipelineState === 'awaiting_validation' && (
                <button
                  onClick={handleManualValidate}
                  className="action-btn success"
                >
                  <span className="btn-icon">?</span>
                  <span>Validate Code Now</span>
                </button>
              )}

              {(pipelineState === 'validation_result' || pipelineState === 'awaiting_regen') && validationResult && (
                <>
                  <button
                    onClick={() => {
                      setPipelineState('done');
                      addActivity('success', 'System', `? Code accepted by user (Score: ${validationResult.quality_score}/100)`);
                    }}
                    className="action-btn success"
                  >
                    <span className="btn-icon">?</span>
                    <span>Accept Code</span>
                  </button>
                  <button
                    onClick={handleManualRegenerate}
                    className="action-btn warning"
                  >
                    <span className="btn-icon"></span>
                    <span>Regenerate Code (Iteration {iteration + 1})</span>
                  </button>
                </>
              )}

              {(pipelineState === 'generating_code' || pipelineState === 'regenerating_code') && (
                <div className="status-indicator generating">
                  <span className="spinner"></span>
                  <span>Generating code...</span>
                </div>
              )}

              {pipelineState === 'validating_code' && (
                <div className="status-indicator validating">
                  <span className="spinner"></span>
                  <span>Validating code...</span>
                </div>
              )}

              {pipelineState === 'done' && (
                <div className="status-indicator success">
                  <span></span>
                  <span>Pipeline Complete!</span>
                </div>
              )}

              {pipelineState === 'failed_final' && (
                <div className="status-indicator error">
                  <span></span>
                  <span>Generation failed - Please try again</span>
                </div>
              )}
            </div>
          </div>


          {drafts.length > 0 && (
            <div className="card">
              <h3>Drafts (Not Validated)</h3>
              <div className="drafts-list">
                {drafts.map((draft: any) => (
                  <div key={draft.draft_id} className="draft-card">
                    <div className="draft-meta">
                      <span className="badge badge-warning">Generated (Not Validated)</span>
                      <span className="draft-id">draft_id: {draft.draft_id}</span>
                      <span className="draft-id">context: {draft.context_id}</span>
                      <span className="draft-id">source: {draft.source}</span>
                    </div>
                    <pre className="draft-output">{draft.generated_output}</pre>
                    <div className="draft-actions">
                      <button
                        className="action-btn primary"
                        onClick={() => handleSubmitDraft(draft)}
                        disabled={isLoading}
                      >
                        <span className="btn-icon">?.</span>
                        <span>Send to Validator Pipeline</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* A2A Communication Log - Timeline view using agent telemetry */}
          {telemetryEvents.length > 0 && (
            <div className="card a2a-section-main">
              <A2ACommunicationLog events={telemetryEvents} />
            </div>
          )}
          {/* Generate MCP from Database */}
          <DBMCPGenerator />

          {/* MongoDB MCP Servers */}
          <MongoMCPServers />

          {/* API Chat - aligned with main column content */}
          {tools.length > 0 && (
            <div className="card chat-panel-card">
              <ChatPanel tools={tools} />
            </div>
          )}

          {/* Error Display */}
          {error && (
            <div className="error-banner">
              <span className="error-icon"></span>
              <span>{error}</span>
              <button onClick={() => setError(null)} className="error-close"></button>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default App;








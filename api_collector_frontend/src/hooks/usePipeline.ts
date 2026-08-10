import { useState, useCallback } from 'react';

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

interface UsePipelineOptions {
  orchestratorUrl?: string;
}

export function usePipeline({ orchestratorUrl = 'http://127.0.0.1:8100' }: UsePipelineOptions = {}) {
  const [contextId, setContextId] = useState<string | null>(null);
  const [state, setState] = useState<PipelineState>('initial');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startPipeline = useCallback(async (sourceType: string, sourceData: string) => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch(`${orchestratorUrl}/pipeline/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_type: sourceType, source_data: sourceData })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      setContextId(data.context_id);
      setState('input_received');

      return data.context_id;
    } catch (err: any) {
      setError(err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [orchestratorUrl]);

  const triggerValidation = useCallback(async (manual: boolean = true) => {
    if (!contextId) {
      throw new Error('No active pipeline context');
    }

    try {
      const response = await fetch(`${orchestratorUrl}/pipeline/${contextId}/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ manual })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (err: any) {
      setError(err.message);
      throw err;
    }
  }, [contextId, orchestratorUrl]);

  const triggerRegeneration = useCallback(async (manual: boolean = true) => {
    if (!contextId) {
      throw new Error('No active pipeline context');
    }

    try {
      const response = await fetch(`${orchestratorUrl}/pipeline/${contextId}/regenerate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ manual })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (err: any) {
      setError(err.message);
      throw err;
    }
  }, [contextId, orchestratorUrl]);

  const getStatus = useCallback(async () => {
    if (!contextId) {
      return null;
    }

    try {
      const response = await fetch(`${orchestratorUrl}/pipeline/${contextId}/status`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const status = await response.json();
      setState(status.state);
      return status;
    } catch (err: any) {
      console.error('Failed to get status:', err);
      return null;
    }
  }, [contextId, orchestratorUrl]);

  const reset = useCallback(() => {
    setContextId(null);
    setState('initial');
    setError(null);
  }, []);

  return {
    contextId,
    state,
    loading,
    error,
    startPipeline,
    triggerValidation,
    triggerRegeneration,
    getStatus,
    reset
  };
}

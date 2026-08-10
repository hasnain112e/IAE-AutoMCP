// Edited by Dr. Wasim
/**
 * Backend URL auto-detection and connection utilities.
 * 
 * Automatically detects backend URL and provides connection checking utilities.
 */

export interface BackendReadyResponse {
  backend: "ready" | "unavailable" | "healthy" | boolean;
  status?: "healthy" | "ready" | "unavailable";
  validator?: "ready" | "unavailable" | "healthy" | boolean;
  orchestrator?: "ready" | "unavailable" | "healthy" | boolean;
  generator?: "ready" | "unavailable" | "healthy" | boolean;
  version?: string;
  env?: {
    google_api_key: boolean;
    openai_api_key: boolean;
  };
}

/**
 * Get backend URL with auto-detection.
 * 
 * Tries in order:
 * 1. Environment variable VITE_BACKEND_URL
 * 2. http://localhost:8000
 * 3. http://127.0.0.1:8000
 * 
 * @returns Backend URL string
 */
export function getBackendUrl(): string {
  // Check environment variable first
  const envUrl = import.meta.env.VITE_BACKEND_URL;
  if (envUrl) {
    return envUrl;
  }
  
  // Try localhost first
  const localhostUrl = "http://localhost:8000";
  const localhost127Url = "http://127.0.0.1:8000";
  
  // Return localhost as default (browser will handle resolution)
  return localhostUrl;
}

/**
 * Check backend connection.
 * 
 * @param url Optional backend URL (defaults to getBackendUrl())
 * @param timeout Optional timeout in milliseconds (default: 5000)
 * @returns Promise that resolves to true if backend is reachable
 */
export async function checkBackendConnection(
  url?: string,
  timeout: number = 5000
): Promise<boolean> {
  const backendUrl = url || getBackendUrl();
  const readyUrl = `${backendUrl}/ready`;
  
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);
    
    const response = await fetch(readyUrl, {
      method: "GET",
      signal: controller.signal,
      headers: {
        "Accept": "application/json",
      },
    });
    
    clearTimeout(timeoutId);
    
    if (response.ok) {
      const data: BackendReadyResponse = await response.json();
      return data.backend === "ready";
    }
    
    return false;
  } catch (error) {
    // Network error, connection refused, timeout, etc.
    return false;
  }
}

/**
 * Wait for backend to become ready.
 * 
 * Polls /ready endpoint until backend reports ready or max attempts reached.
 * 
 * @param url Optional backend URL (defaults to getBackendUrl())
 * @param interval Polling interval in milliseconds (default: 500)
 * @param maxAttempts Maximum number of attempts (default: 20)
 * @param onProgress Optional callback for progress updates
 * @returns Promise that resolves to BackendReadyResponse when ready, or null if max attempts reached
 */
export async function waitForBackendReady(
  url?: string,
  interval: number = 500,
  maxAttempts: number = 20,
  onProgress?: (attempt: number, maxAttempts: number) => void
): Promise<BackendReadyResponse | null> {
  const backendUrl = url || getBackendUrl();
  const readyUrl = `${backendUrl}/ready`;
  
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    if (onProgress) {
      onProgress(attempt, maxAttempts);
    }
    
    try {
      const response = await fetch(readyUrl, {
        method: "GET",
        headers: {
          "Accept": "application/json",
        },
      });
      
      if (response.ok) {
        const data: BackendReadyResponse = await response.json();
        if (data.backend === "ready") {
          return data;
        }
      }
    } catch (error) {
      // Continue polling on error
    }
    
    // Wait before next attempt (except on last attempt)
    if (attempt < maxAttempts) {
      await new Promise((resolve) => setTimeout(resolve, interval));
    }
  }
  
  return null;
}

/**
 * Get backend readiness status.
 * 
 * @param url Optional backend URL (defaults to getBackendUrl())
 * @returns Promise that resolves to BackendReadyResponse or null if unreachable
 */
export async function getBackendStatus(
  url?: string
): Promise<BackendReadyResponse | null> {
  const backendUrl = url || getBackendUrl();
  const readyUrl = `${backendUrl}/ready`;
  
  try {
    const response = await fetch(readyUrl, {
      method: "GET",
      headers: {
        "Accept": "application/json",
      },
    });
    
    if (response.ok) {
      return await response.json() as BackendReadyResponse;
    }
    
    return null;
  } catch (error) {
    return null;
  }
}


/**
 * Centralized Axios instance with interceptors and retry logic.
 * 
 * Features:
 * - Base URL from backend.ts
 * - Request timeout (8 seconds)
 * - Automatic retry on ECONNREFUSED
 * - Global interceptors for error handling
 */

import axios, { AxiosInstance, AxiosError, AxiosRequestConfig, InternalAxiosRequestConfig } from "axios";
import { getBackendUrl } from "./backend";

// Create axios instance with base configuration
const axiosInstance: AxiosInstance = axios.create({
  baseURL: getBackendUrl(),
  timeout: 8000, // 8 seconds
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/json",
  },
});

// Request interceptor
axiosInstance.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Update base URL in case it changed
    if (!config.baseURL) {
      config.baseURL = getBackendUrl();
    }
    return config;
  },
  (error: AxiosError) => {
    return Promise.reject(error);
  }
);

// Response interceptor for error handling
axiosInstance.interceptors.response.use(
  (response) => {
    return response;
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };
    
    // Handle network errors (ECONNREFUSED, timeout, etc.)
    if (
      !error.response &&
      (error.code === "ECONNREFUSED" ||
        error.code === "ETIMEDOUT" ||
        error.message.includes("Network Error") ||
        error.message.includes("timeout"))
    ) {
      // Retry logic for connection errors
      if (originalRequest && !originalRequest._retry) {
        originalRequest._retry = true;
        
        // Wait a bit before retry
        await new Promise((resolve) => setTimeout(resolve, 1000));
        
        // Retry the request
        return axiosInstance(originalRequest);
      }
      
      // Emit global event for connection loss
      window.dispatchEvent(new CustomEvent("backend-connection-lost", {
        detail: { error: error.message },
      }));
      
      // Return a structured error
      return Promise.reject({
        type: "network_error",
        message: "Backend connection failed. Please check if the server is running.",
        originalError: error,
      });
    }
    
    // Handle HTTP errors
    if (error.response) {
      const status = error.response.status;
      
      // 500 errors - show toast
      if (status >= 500) {
        window.dispatchEvent(new CustomEvent("show-toast", {
          detail: {
            type: "error",
            message: `Server error: ${error.response.data?.detail || "Internal server error"}`,
          },
        }));
      }
      
      // 404 errors - show dev warning
      if (status === 404) {
        if (import.meta.env.DEV) {
          console.warn("API endpoint not found:", error.config?.url);
        }
      }
      
      // 401/403 errors - authentication issues
      if (status === 401 || status === 403) {
        window.dispatchEvent(new CustomEvent("show-toast", {
          detail: {
            type: "warning",
            message: "Authentication required or access denied",
          },
        }));
      }
    }
    
    return Promise.reject(error);
  }
);

export default axiosInstance;


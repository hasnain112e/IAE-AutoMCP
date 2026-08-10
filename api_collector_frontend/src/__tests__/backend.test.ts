/**
 * Unit tests for backend connectivity layer.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  getBackendUrl,
  checkBackendConnection,
  waitForBackendReady,
  getBackendStatus,
  BackendReadyResponse,
} from "../api/backend";

// Mock fetch
global.fetch = vi.fn();

describe("Backend Connectivity", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset environment
    delete import.meta.env.VITE_BACKEND_URL;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("getBackendUrl", () => {
    it("should return environment variable URL if set", () => {
      import.meta.env.VITE_BACKEND_URL = "http://custom-backend:9000";
      expect(getBackendUrl()).toBe("http://custom-backend:9000");
    });

    it("should return localhost URL by default", () => {
      expect(getBackendUrl()).toBe("http://localhost:8000");
    });
  });

  describe("checkBackendConnection", () => {
    it("should return true when backend is available", async () => {
      const mockResponse: BackendReadyResponse = {
        backend: "ready",
        validator: "ready",
        orchestrator: "ready",
        generator: "ready",
        env: {
          google_api_key: true,
          openai_api_key: true,
        },
      };

      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await checkBackendConnection();
      expect(result).toBe(true);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/ready"),
        expect.any(Object)
      );
    });

    it("should return false when backend is unavailable", async () => {
      (global.fetch as any).mockRejectedValueOnce(new Error("Network error"));

      const result = await checkBackendConnection();
      expect(result).toBe(false);
    });

    it("should return false on timeout", async () => {
      (global.fetch as any).mockImplementationOnce(
        () =>
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error("Timeout")), 100)
          )
      );

      const result = await checkBackendConnection(undefined, 50);
      expect(result).toBe(false);
    });
  });

  describe("waitForBackendReady", () => {
    it("should return status when backend becomes ready", async () => {
      const mockResponse: BackendReadyResponse = {
        backend: "ready",
        validator: "ready",
        orchestrator: "ready",
        generator: "ready",
        env: {
          google_api_key: true,
          openai_api_key: true,
        },
      };

      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await waitForBackendReady(undefined, 100, 5);
      expect(result).toEqual(mockResponse);
    });

    it("should return null after max attempts", async () => {
      (global.fetch as any).mockRejectedValue(new Error("Network error"));

      const result = await waitForBackendReady(undefined, 50, 3);
      expect(result).toBeNull();
    });

    it("should call onProgress callback", async () => {
      const onProgress = vi.fn();
      const mockResponse: BackendReadyResponse = {
        backend: "ready",
        validator: "ready",
        orchestrator: "ready",
        generator: "ready",
        env: {
          google_api_key: true,
          openai_api_key: true,
        },
      };

      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      await waitForBackendReady(undefined, 50, 5, onProgress);
      expect(onProgress).toHaveBeenCalled();
    });
  });

  describe("getBackendStatus", () => {
    it("should return status when backend is reachable", async () => {
      const mockResponse: BackendReadyResponse = {
        backend: "ready",
        validator: "unavailable",
        orchestrator: "ready",
        generator: "ready",
        env: {
          google_api_key: false,
          openai_api_key: true,
        },
      };

      (global.fetch as any).mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      });

      const result = await getBackendStatus();
      expect(result).toEqual(mockResponse);
    });

    it("should return null when backend is unreachable", async () => {
      (global.fetch as any).mockRejectedValueOnce(new Error("Network error"));

      const result = await getBackendStatus();
      expect(result).toBeNull();
    });
  });
});


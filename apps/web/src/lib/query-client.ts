import { QueryClient, type QueryClientConfig } from "@tanstack/react-query";
import { ApiError, SessionExpiredError } from "./api";

export const queryClientDefaults: QueryClientConfig = {
  defaultOptions: {
    queries: {
      // Only retry transient failures (network / 5xx). A 4xx (esp. 401 on
      // `/me` when signed out or holding a stale token) is terminal — retrying
      // it just doubles the request and the refresh-or-signout cycle, which is
      // what produced the repeated `GET /api/me 401` storm at load.
      retry: (failureCount, error) => {
        if (error instanceof SessionExpiredError) return false;
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
          return false;
        }
        return failureCount < 1;
      },
      staleTime: 30_000,
    },
  },
};

export const queryClient = new QueryClient(queryClientDefaults);

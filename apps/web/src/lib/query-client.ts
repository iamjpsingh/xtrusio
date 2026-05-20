import { QueryClient, type QueryClientConfig } from "@tanstack/react-query";

export const queryClientDefaults: QueryClientConfig = {
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
};

export const queryClient = new QueryClient(queryClientDefaults);

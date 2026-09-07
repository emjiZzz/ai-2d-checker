import { useQuery, useMutation, useQueryClient, type QueryFunctionContext } from "@tanstack/react-query";
import { fetchClients, createClient as createClientApi, deleteClient as deleteClientApi } from "../services/clientsApi";
import { clientKeys } from "../services/queryKeys";
import type { ClientItem } from "../stores/workspaceStore";

export function useClients() {
  const queryClient = useQueryClient();

  // 1. Fetch
  const { data: clients = [], isLoading, isFetching, error } = useQuery<ClientItem[], Error>({
    queryKey: clientKeys.list(),
    queryFn: ({ signal }: QueryFunctionContext) => fetchClients(signal),
  });

  // 2. Create
  const createMutation = useMutation<void, Error, string>({
    mutationFn: (name) => createClientApi(name),
    onMutate: async (newClientName) => {
      await queryClient.cancelQueries({ queryKey: clientKeys.list() });
      const previousClients = queryClient.getQueryData<ClientItem[]>(clientKeys.list()) || [];

      // Optimistic update
      queryClient.setQueryData<ClientItem[]>(clientKeys.list(), [
        ...previousClients,
        { id: `temp-${Date.now()}`, name: newClientName, created_at: new Date().toISOString() },
      ]);

      return { previousClients };
    },
    onError: (_err, _variables, context: any) => {
      if (context?.previousClients) {
        queryClient.setQueryData(clientKeys.list(), context.previousClients);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: clientKeys.list() });
    },
  });

  // 3. Delete
  const deleteMutation = useMutation<void, Error, string>({
    mutationFn: (name) => deleteClientApi(name),
    onMutate: async (deletedClientName) => {
      await queryClient.cancelQueries({ queryKey: clientKeys.list() });
      const previousClients = queryClient.getQueryData<ClientItem[]>(clientKeys.list()) || [];

      // Optimistic update
      queryClient.setQueryData<ClientItem[]>(
        clientKeys.list(),
        previousClients.filter((c) => c.name !== deletedClientName)
      );

      return { previousClients };
    },
    onError: (_err, _variables, context: any) => {
      if (context?.previousClients) {
        queryClient.setQueryData(clientKeys.list(), context.previousClients);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: clientKeys.list() });
    },
  });

  return {
    clients,
    isLoading,
    isFetching,
    error,
    createClient: createMutation.mutateAsync,
    deleteClient: deleteMutation.mutateAsync,
    isCreating: createMutation.isPending,
    isDeleting: deleteMutation.isPending,
  };
}

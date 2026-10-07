"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { errorMessage } from "@/lib/api/errors";

import { countryKeys } from "../queries";

/**
 * One mutation for every write on the countries pages: run `fn`, say
 * `done`, and re-read every country query, since a level's expected types
 * and a country's type rows depend on the global tables.
 */
export function useCountryMutation<TArgs, TResult>(
  fn: (args: TArgs) => Promise<TResult>,
  done: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      toast.success(done);
      await queryClient.invalidateQueries({ queryKey: countryKeys.all });
    },
    onError: (error) => toast.error(errorMessage(error)),
  });
}

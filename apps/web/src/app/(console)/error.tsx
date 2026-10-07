"use client";

import { AlertCircleIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api/errors";

export default function ConsoleError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4">
      <Alert variant="destructive">
        <AlertCircleIcon />
        <AlertTitle>Something went wrong</AlertTitle>
        <AlertDescription>{errorMessage(error)}</AlertDescription>
      </Alert>
      <Button variant="outline" className="self-start" onClick={reset}>
        Try again
      </Button>
    </div>
  );
}

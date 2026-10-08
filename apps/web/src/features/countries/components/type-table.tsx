"use client";

import { revalidateLogic } from "@tanstack/react-form";
import { PencilIcon, PlusIcon, Trash2Icon } from "lucide-react";
import { useState } from "react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { useAppForm } from "@/components/shared/form";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { errorMessage } from "@/lib/api/errors";
import { humanize } from "@/lib/labels";

import { useCountryMutation } from "../hooks/use-country-mutations";
import { typeSchema, type TypeFormInput } from "../schemas";
import { FormDialog } from "./form-dialog";

interface TypeRow {
  name: string;
  description: string;
}

/** The global institution types or source types: a name and what it means. */
export function TypeTable({
  noun,
  rows,
  put,
  remove,
}: {
  /** "institution type" or "source type", for the buttons and messages. */
  noun: string;
  rows: TypeRow[];
  put: (body: TypeRow) => Promise<unknown>;
  remove: (name: string) => Promise<unknown>;
}) {
  const [editing, setEditing] = useState<TypeRow | "new" | null>(null);
  const [deleting, setDeleting] = useState<TypeRow | null>(null);
  const deletion = useCountryMutation(remove, `${humanize(noun)} deleted`);
  const sorted = [...rows].sort((a, b) => a.name.localeCompare(b.name));

  return (
    <div className="flex flex-col gap-3">
      {sorted.length === 0 ? (
        <EmptyState>None yet.</EmptyState>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="w-0" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((row) => (
                <TableRow key={row.name}>
                  <TableCell className="font-medium whitespace-nowrap">
                    {humanize(row.name)}
                    <span className="ml-2 font-mono text-xs text-muted-foreground">{row.name}</span>
                  </TableCell>
                  <TableCell className="min-w-64 max-w-lg whitespace-normal text-muted-foreground">
                    {row.description || "–"}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Edit ${row.name}`}
                        onClick={() => setEditing(row)}
                      >
                        <PencilIcon />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Delete ${row.name}`}
                        onClick={() => setDeleting(row)}
                      >
                        <Trash2Icon />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <div>
        <Button variant="outline" onClick={() => setEditing("new")}>
          <PlusIcon /> Add {noun}
        </Button>
      </div>
      {editing && (
        <TypeDialog
          noun={noun}
          row={editing === "new" ? null : editing}
          put={put}
          onClose={() => setEditing(null)}
        />
      )}
      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title={`Delete the ${deleting ? humanize(deleting.name).toLowerCase() : ""} ${noun}?`}
        description="Refused while a country's tables or a row in the graph still use it."
        pending={deletion.isPending}
        onConfirm={() =>
          deleting && deletion.mutateAsync(deleting.name).then(() => setDeleting(null))
        }
      />
    </div>
  );
}

function TypeDialog({
  noun,
  row,
  put,
  onClose,
}: {
  noun: string;
  row: TypeRow | null;
  put: (body: TypeRow) => Promise<unknown>;
  onClose: () => void;
}) {
  const [serverError, setServerError] = useState<string | null>(null);
  const save = useCountryMutation(put, row ? `${humanize(noun)} saved` : `${humanize(noun)} added`);
  const form = useAppForm({
    defaultValues: {
      name: row?.name ?? "",
      description: row?.description ?? "",
    } satisfies TypeFormInput,
    validationLogic: revalidateLogic(),
    validators: { onDynamic: typeSchema },
    onSubmit: async ({ value }) => {
      setServerError(null);
      try {
        await save.mutateAsync(typeSchema.parse(value));
        onClose();
      } catch (error) {
        setServerError(errorMessage(error));
      }
    },
  });
  return (
    <FormDialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={row ? `Edit ${humanize(row.name).toLowerCase()}` : `Add ${noun}`}
      form={form}
      serverError={serverError}
      submit={
        <form.AppForm>
          <form.SubmitButton>{row ? "Save" : "Add"}</form.SubmitButton>
        </form.AppForm>
      }
    >
      <form.AppField name="name">
        {(field) => (
          <field.TextField
            label="Name"
            required
            placeholder="school_board"
            autoComplete="off"
            disabled={row !== null}
            description="The key the tables and the agent use; lowercase with underscores."
          />
        )}
      </form.AppField>
      <form.AppField name="description">
        {(field) => (
          <field.TextareaField
            label="Description"
            rows={3}
            description="What the agent is told the type means."
          />
        )}
      </form.AppField>
    </FormDialog>
  );
}

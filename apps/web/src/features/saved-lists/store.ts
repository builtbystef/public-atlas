"use client";

import { useSyncExternalStore } from "react";

import type { Database } from "@/lib/api/database";

import {
  addList,
  mergeLists,
  parseStoredLists,
  removeList,
  replaceList,
  serializeLists,
  type SavedList,
  type SavedListInput,
} from "./schemas";

/**
 * The saved lists live in this browser's localStorage, one key per database:
 * a list names places and types by id, and the live and eval databases do
 * not share ids. Other tabs see a change through the `storage` event; this
 * tab through the listeners below.
 */

const storageKey = (database: Database) => `public-atlas:saved-lists:v1:${database}`;

const listeners = new Set<() => void>();

function notify() {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key.startsWith("public-atlas:saved-lists:")) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

function readRaw(database: Database): string | null {
  try {
    return window.localStorage.getItem(storageKey(database));
  } catch {
    // Storage can be blocked outright (a locked-down browser, some private windows).
    return null;
  }
}

// useSyncExternalStore wants the same array back while nothing changed, so
// the parse is kept per key and redone only when the stored string differs.
const cache = new Map<string, { raw: string | null; lists: SavedList[] }>();

function snapshot(database: Database): SavedList[] {
  const raw = readRaw(database);
  const cached = cache.get(database);
  if (cached && cached.raw === raw) return cached.lists;
  const lists = parseStoredLists(raw);
  cache.set(database, { raw, lists });
  return lists;
}

function write(database: Database, lists: SavedList[]) {
  // Throws when storage is full or blocked; callers say so.
  window.localStorage.setItem(storageKey(database), serializeLists(lists));
  notify();
}

/**
 * The saved lists of `database`, newest first; null until the browser has
 * read them, since the server cannot, so a page shows a skeleton rather than
 * a flash of "no lists".
 */
export function useSavedLists(database: Database): SavedList[] | null {
  return useSyncExternalStore(
    subscribe,
    () => snapshot(database),
    () => null,
  );
}

/** One list by id: undefined while unread, null when this browser has no such list. */
export function useSavedList(database: Database, id: string): SavedList | null | undefined {
  const lists = useSavedLists(database);
  if (lists === null) return undefined;
  return lists.find((list) => list.id === id) ?? null;
}

/** The writes. Each reads the store afresh, so a change made in another tab is kept. */
export function savedListActions(database: Database) {
  const now = () => new Date().toISOString();
  return {
    create(input: SavedListInput): SavedList {
      const { lists, list } = addList(snapshot(database), input, {
        id: crypto.randomUUID(),
        now: now(),
      });
      write(database, lists);
      return list;
    },
    update(id: string, input: SavedListInput) {
      write(database, replaceList(snapshot(database), id, input, now()));
    },
    remove(id: string) {
      write(database, removeList(snapshot(database), id));
    },
    /** Merges an exported file in; null when it is not one. */
    importFile(raw: string): number | null {
      const merged = mergeLists(snapshot(database), raw);
      if (merged === null) return null;
      write(database, merged.lists);
      return merged.imported;
    },
    exportFile(): string {
      return serializeLists(snapshot(database));
    },
  };
}

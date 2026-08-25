import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Human-readable message for an unknown thrown value. */
export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

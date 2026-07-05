import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

// The ONE sanctioned grab-bag export (CLAUDE.md): shadcn's class-merge helper.
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** shadcn/ui convention — merge conditional class names safely. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

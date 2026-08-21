import { Check } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * A short confirmation that something was saved.
 *
 * Deliberately small and self-dismissing: it says the work landed and then
 * gets out of the way. It never reports failures — an error stays on screen
 * next to what caused it, where it can be read and acted on.
 */
export function Toast({ show, message }: { show: boolean; message: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'pointer-events-none fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-lg',
        'border border-positive/30 bg-positive px-4 py-2.5 text-sm font-medium text-white shadow-lg',
        'transition-all duration-200',
        show ? 'translate-y-0 opacity-100' : 'pointer-events-none translate-y-2 opacity-0',
      )}
    >
      <Check className="h-4 w-4" aria-hidden />
      {message}
    </div>
  )
}

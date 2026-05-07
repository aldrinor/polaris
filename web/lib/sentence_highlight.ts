// I-f5-001 — debounced sentence-hover hook for VerifiedReportView.

import { useEffect, useRef, useState } from "react";

interface UseSentenceHoverOpts {
  selector?: string;
  debounceMs?: number;
}

export function useSentenceHover(opts: UseSentenceHoverOpts = {}) {
  const selector = opts.selector ?? "[data-sentence-id]";
  const debounce_ms = opts.debounceMs ?? 50;
  const [hovered_id, set_hovered_id] = useState<string | null>(null);
  const root_ref = useRef<HTMLDivElement | null>(null);
  const timer_ref = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const root = root_ref.current;
    if (!root) return;

    const schedule = (id: string | null) => {
      if (timer_ref.current) clearTimeout(timer_ref.current);
      timer_ref.current = setTimeout(() => set_hovered_id(id), debounce_ms);
    };

    const on_over = (ev: Event) => {
      const target = ev.target as HTMLElement | null;
      const el = target?.closest(selector) as HTMLElement | null;
      if (!el) return;
      const id = el.getAttribute("data-sentence-id");
      if (id) schedule(id);
    };
    const on_out = (ev: Event) => {
      const related = (ev as MouseEvent).relatedTarget as HTMLElement | null;
      if (related && root.contains(related) && related.closest(selector))
        return;
      schedule(null);
    };

    root.addEventListener("mouseover", on_over);
    root.addEventListener("mouseout", on_out);
    return () => {
      root.removeEventListener("mouseover", on_over);
      root.removeEventListener("mouseout", on_out);
      if (timer_ref.current) clearTimeout(timer_ref.current);
    };
  }, [selector, debounce_ms]);

  return { hovered_id, root_ref };
}

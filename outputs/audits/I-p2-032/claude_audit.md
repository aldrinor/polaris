# Claude audit — I-p2-032 (#787)
Fixed circular --font-sans (live serif fallback site-wide, incl. flagship headline). One-line: var(--font-sans)→var(--font-geist-sans). Screenshot-verified Geist Sans. This bug is the proof my prior per-page verification was inadequate — pivoting to a rigorous live Playwright audit next.

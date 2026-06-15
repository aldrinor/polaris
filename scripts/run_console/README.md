# POLARIS run console (standalone, read-only)

Minimal live view of a running `run_honest_sweep_r3.py` benchmark as one
chronological scrolling log, plus a PG_* env-config panel. Reads run
observability files only; never imports or modifies pipeline code.

Run:

    python scripts/run_console/run_console.py --host 127.0.0.1 --port 8787 --root outputs/honest_sweep_r3

Then open http://127.0.0.1:8787/ . Host/port/root also read from
`PG_CONSOLE_HOST` / `PG_CONSOLE_PORT` / `PG_CONSOLE_ROOT`.

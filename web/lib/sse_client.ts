// I-f4-001 — SSE consumer with reconnect/backoff. Tested library; not yet wired into subscribeToRun() (I-f4-001a).

export interface SSEClientOpts {
  initialBackoffMs?: number;
  maxBackoffMs?: number;
  maxRetries?: number;
  eventNames?: string[];
  onMessage?: (data: string) => void;
  onEvent?: (name: string, data: string) => void;
  onOpen?: () => void;
  onError?: (err: { terminal: boolean; attempts: number }) => void;
  onReconnect?: (attempts: number) => void;
}

export class SSEClient {
  private _es: EventSource | null = null;
  private _attempts = 0;
  private _total_connects = 0;
  private _closed = false;
  private _received_message = false;
  private _timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private url: string,
    private opts: SSEClientOpts = {},
  ) {}

  connect(): void {
    if (this._closed) return;
    this._received_message = false;
    this._total_connects += 1;
    const es = new EventSource(this.url);
    this._es = es;
    es.onopen = () => this.opts.onOpen?.();
    es.onmessage = (ev: MessageEvent) => {
      this._received_message = true;
      this._attempts = 0;
      this.opts.onMessage?.(ev.data);
    };
    for (const name of this.opts.eventNames ?? []) {
      es.addEventListener(name, (ev) => {
        this._received_message = true;
        this._attempts = 0;
        this.opts.onEvent?.(name, (ev as MessageEvent).data);
      });
    }
    es.onerror = () => {
      es.close();
      this._es = null;
      if (this._closed) return;
      const max_retries = this.opts.maxRetries ?? 10;
      if (this._attempts >= max_retries && !this._received_message) {
        this.opts.onError?.({ terminal: true, attempts: this._attempts });
        this._closed = true;
        return;
      }
      const initial = this.opts.initialBackoffMs ?? 200;
      const cap = this.opts.maxBackoffMs ?? 1000;
      const delay = Math.min(initial * 2 ** this._attempts, cap);
      this._attempts += 1;
      this.opts.onError?.({ terminal: false, attempts: this._attempts });
      this._timer = setTimeout(() => {
        this.opts.onReconnect?.(this._attempts);
        this.connect();
      }, delay);
    };
  }

  close(): void {
    this._closed = true;
    if (this._timer) clearTimeout(this._timer);
    this._timer = null;
    this._es?.close();
    this._es = null;
  }

  getAttempts(): number {
    return this._attempts;
  }

  getTotalConnects(): number {
    return this._total_connects;
  }

  getReadyState(): number {
    return this._es?.readyState ?? -1;
  }
}

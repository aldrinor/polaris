// I-f4-003 — Same-origin multi-tab cancel propagation via BroadcastChannel.

export interface RunBroadcastOpts {
  onCancel?: () => void;
}

export class RunBroadcast {
  private _channel: BroadcastChannel | null = null;

  constructor(
    private run_id: string,
    private opts: RunBroadcastOpts = {},
  ) {}

  subscribe(): void {
    if (typeof BroadcastChannel === "undefined") return;
    this._channel = new BroadcastChannel(`polaris-run-${this.run_id}`);
    this._channel.onmessage = (ev: MessageEvent) => {
      if (ev.data?.type === "cancel") {
        this.opts.onCancel?.();
      }
    };
  }

  broadcastCancel(): void {
    this._channel?.postMessage({ type: "cancel" });
  }

  close(): void {
    this._channel?.close();
    this._channel = null;
  }
}

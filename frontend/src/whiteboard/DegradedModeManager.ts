export type WhiteboardMode = "ONLINE_FULL" | "DEGRADED_NO_AI" | "DEGRADED_LOCAL_ONLY";

export class DegradedModeManager {
  private mode: WhiteboardMode = "ONLINE_FULL";

  get currentMode(): WhiteboardMode {
    return this.mode;
  }

  canWriteFreehand(): true {
    return true;
  }

  connectionLost(): void {
    this.mode = "DEGRADED_LOCAL_ONLY";
  }

  aiUnavailable(): void {
    if (this.mode === "ONLINE_FULL") this.mode = "DEGRADED_NO_AI";
  }

  reconnected(aiAvailable = true): void {
    this.mode = aiAvailable ? "ONLINE_FULL" : "DEGRADED_NO_AI";
  }
}

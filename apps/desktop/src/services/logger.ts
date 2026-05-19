/**
 * Frontend Logging Abstraction Layer for AI-2D-Checker.
 * Dispatches logs securely over IPC to the persistent Rust logging subsystem
 * when running inside Tauri, and falls back to standard console logging in web contexts.
 */

const isTauri = typeof window !== "undefined" && !!(window as any).__TAURI_INTERNALS__;

async function dispatchLog(level: "info" | "warn" | "error" | "debug", message: string) {
    const timestamp = new Date().toISOString();
    const formatted = `[${timestamp}] [${level.toUpperCase()}] (FrontendUI) ${message}`;

    // 1. Fallback to standard console logger for development and browser diagnostic purposes
    switch (level) {
        case "info":
            console.info(formatted);
            break;
        case "warn":
            console.warn(formatted);
            break;
        case "error":
            console.error(formatted);
            break;
        case "debug":
            console.debug(formatted);
            break;
    }

    // 2. Dispatch log over IPC to the Rust app tracing subsystem
    if (isTauri) {
        try {
            const { invoke } = await import("@tauri-apps/api/core");
            await invoke("log_from_frontend", { level, message });
        } catch (err) {
            console.warn("Failed to dispatch log over Tauri IPC bridge:", err);
        }
    }
}

export const logger = {
    info: (message: string) => dispatchLog("info", message),
    warn: (message: string) => dispatchLog("warn", message),
    error: (message: string) => dispatchLog("error", message),
    debug: (message: string) => dispatchLog("debug", message)
};

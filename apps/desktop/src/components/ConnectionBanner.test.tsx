/**
 * Tests for the offline overlay's prototype-only backend-address field.
 *
 * `SystemDiagnostics`, inside `SettingsView`, is the only other caller of `setBackendUrl`, and a
 * prototype build cannot reach Settings — the header nav strip is hidden wholesale and
 * `currentNav` is pinned to "workspace". So without this field a prototype build could report
 * "Connection Lost" and retry forever against an address the user could neither see nor change.
 */
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConnectionBanner } from "./ConnectionBanner";
import { useConnectionStore } from "../stores/connectionStore";

const goOffline = () => useConnectionStore.setState({ status: "offline" });

beforeEach(() => {
  useConnectionStore.setState({ backendUrl: "http://127.0.0.1:8080" });
  vi.spyOn(useConnectionStore.getState(), "checkHealth").mockResolvedValue(undefined as never);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  useConnectionStore.setState({ status: "online" });
});

describe("ConnectionBanner", () => {
  it("shows Connection Lost and retry button when offline", () => {
    goOffline();
    render(<ConnectionBanner />);

    expect(screen.getByText("Connection Lost")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry Connection" })).toBeInTheDocument();
  });

  it("does not render backend address or API token input fields", () => {
    goOffline();
    render(<ConnectionBanner />);

    expect(screen.queryByLabelText("Backend Address")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("API Token (Remote Backend)")).not.toBeInTheDocument();
  });

  it("is absent while the connection is healthy — the overlay itself does not render", () => {
    useConnectionStore.setState({ status: "online" });
    const { container } = render(<ConnectionBanner />);

    expect(container).toBeEmptyDOMElement();
  });
});

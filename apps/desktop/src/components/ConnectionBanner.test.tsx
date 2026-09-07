/**
 * Tests for the offline overlay's prototype-only backend-address field.
 *
 * `SystemDiagnostics`, inside `SettingsView`, is the only other caller of `setBackendUrl`, and a
 * prototype build cannot reach Settings — the header nav strip is hidden wholesale and
 * `currentNav` is pinned to "workspace". So without this field a prototype build could report
 * "Connection Lost" and retry forever against an address the user could neither see nor change.
 */
import { render, screen, fireEvent } from "@testing-library/react";
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

describe("ConnectionBanner — full build", () => {
  it("offers no address field, because Settings owns that control", () => {
    goOffline();
    render(<ConnectionBanner />);

    expect(screen.getByText("Connection Lost")).toBeInTheDocument();
    expect(screen.queryByLabelText("Backend Address")).not.toBeInTheDocument();
  });
});

describe("ConnectionBanner — prototype build", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_PROTOTYPE_MODE", "true");
  });

  it("shows the address it is retrying against", () => {
    goOffline();
    render(<ConnectionBanner />);

    expect(screen.getByLabelText("Backend Address")).toHaveValue("http://127.0.0.1:8080");
  });

  it("applies a corrected address to the store", () => {
    const setBackendUrl = vi.fn();
    useConnectionStore.setState({ setBackendUrl } as never);
    goOffline();
    render(<ConnectionBanner />);

    fireEvent.change(screen.getByLabelText("Backend Address"), {
      target: { value: "http://127.0.0.1:9001" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));

    expect(setBackendUrl).toHaveBeenCalledWith("http://127.0.0.1:9001");
  });

  it("accepts Enter as well as the button", () => {
    const setBackendUrl = vi.fn();
    useConnectionStore.setState({ setBackendUrl } as never);
    goOffline();
    render(<ConnectionBanner />);

    const field = screen.getByLabelText("Backend Address");
    fireEvent.change(field, { target: { value: "http://10.0.0.4:8080" } });
    fireEvent.keyDown(field, { key: "Enter" });

    expect(setBackendUrl).toHaveBeenCalledWith("http://10.0.0.4:8080");
  });

  it("will not apply an unchanged or blank address", () => {
    goOffline();
    render(<ConnectionBanner />);
    const apply = screen.getByRole("button", { name: "Apply" });

    // Unchanged from the store value.
    expect(apply).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Backend Address"), { target: { value: "   " } });
    expect(apply).toBeDisabled();
  });

  it("applies a remote API token to the store", () => {
    const setRemoteApiToken = vi.fn();
    useConnectionStore.setState({ setRemoteApiToken } as never);
    goOffline();
    render(<ConnectionBanner />);

    const tokenInput = screen.getByLabelText("API Token (Remote Backend)");
    fireEvent.change(tokenInput, { target: { value: "test-secret-token-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Token" }));

    expect(setRemoteApiToken).toHaveBeenCalledWith("test-secret-token-123");
  });

  it("is absent while the connection is healthy — the overlay itself does not render", () => {
    useConnectionStore.setState({ status: "online" });
    const { container } = render(<ConnectionBanner />);

    expect(container).toBeEmptyDOMElement();
  });
});

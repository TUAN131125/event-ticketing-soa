import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../../src/auth/AuthProvider";
import { AdminLoginPage } from "../../src/pages/AuthPages";

describe("admin authentication form", () => {
  async function renderLogin() {
    await act(async () => {
      render(
        <MemoryRouter initialEntries={["/login"]}>
          <AuthProvider>
            <AdminLoginPage />
          </AuthProvider>
        </MemoryRouter>,
      );
    });
  }

  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses the same shared input treatment for email and password", async () => {
    await renderLogin();

    const email = screen.getByLabelText("Email");
    const password = screen.getByLabelText("Password");
    expect(email).toHaveClass("ui-control");
    expect(password).toHaveClass("ui-control");
    expect(email).not.toHaveClass("native-input");
  });

  it("keeps borders and connects invalid fields to their messages", async () => {
    await renderLogin();
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const email = screen.getByLabelText("Email");
    const password = screen.getByLabelText("Password");
    await waitFor(() => expect(email).toHaveAttribute("aria-invalid", "true"));
    expect(password).toHaveAttribute("aria-invalid", "true");
    expect(email).toHaveAttribute("aria-describedby", "admin-auth-email-error");
    expect(password).toHaveAttribute(
      "aria-describedby",
      "admin-auth-password-error",
    );
    expect(
      screen.getByRole("button", { name: "Show password" }),
    ).toBeInTheDocument();
  });
});

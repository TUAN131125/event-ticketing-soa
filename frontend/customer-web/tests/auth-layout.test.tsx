import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AuthProvider } from "../src/app/auth";
import { LoginPage, RegisterPage } from "../src/pages/AuthPages";

async function renderAuth(page: "login" | "register") {
  let view!: ReturnType<typeof render>;
  await act(async () => {
    view = render(
      <MemoryRouter initialEntries={[`/${page}`]}>
        <AuthProvider>
          {page === "login" ? <LoginPage /> : <RegisterPage />}
        </AuthProvider>
      </MemoryRouter>,
    );
  });
  return view;
}

describe("customer authentication layout", () => {
  beforeEach(() => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it.each(["login", "register"] as const)(
    "uses the padded auth card and shared field spacing on %s",
    async (page) => {
      const { container } = await renderAuth(page);
      const card = container.querySelector(".auth-card");
      const form = container.querySelector(".auth-card-form");
      expect(card).toHaveClass("ui-card", "ui-card--padded");
      expect(form).toHaveClass("stack-form");
      expect(screen.getByLabelText("Email")).toHaveClass("ui-control");
      expect(screen.getByLabelText("Password")).toHaveClass("ui-control");
    },
  );

  it("links validation errors to both inputs without changing their control class", async () => {
    await renderAuth("login");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    const email = screen.getByLabelText("Email");
    const password = screen.getByLabelText("Password");
    await waitFor(() => expect(email).toHaveAttribute("aria-invalid", "true"));
    expect(password).toHaveAttribute("aria-invalid", "true");
    expect(email).toHaveAttribute(
      "aria-describedby",
      "customer-auth-email-error",
    );
    expect(password).toHaveAttribute(
      "aria-describedby",
      "customer-auth-password-error",
    );
    expect(email).toHaveClass("ui-control");
    expect(password).toHaveClass("ui-control");
  });
});

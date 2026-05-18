import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AuthLayout } from "./auth-layout";

describe("AuthLayout", () => {
  it("renders title, subtitle, children and footer", () => {
    render(
      <AuthLayout title="Welcome back" subtitle="Sign in to your dashboard" footer={<span>foot</span>}>
        <form aria-label="f" />
      </AuthLayout>,
    );
    expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.getByText("Sign in to your dashboard")).toBeInTheDocument();
    expect(screen.getByRole("form", { name: "f" })).toBeInTheDocument();
    expect(screen.getByText("foot")).toBeInTheDocument();
    expect(screen.getByText("Xtrusio")).toBeInTheDocument();
  });

  it("forces the dark theme wrapper", () => {
    const { container } = render(
      <AuthLayout title="t" subtitle="s">
        <div />
      </AuthLayout>,
    );
    expect(container.querySelector(".dark")).not.toBeNull();
  });
});

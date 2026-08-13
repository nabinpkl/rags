// The theme control. "System" is a distinct third choice, not a synonym for
// whichever of light/dark is currently showing — these tests pin that the
// menu reports and sets the CHOICE, since collapsing it into the resolved
// value is the usual way this control gets broken.
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { useTheme } from "next-themes";
import { ThemeMenu } from "@/components/shell/theme-menu";

vi.mock("next-themes");

const useThemeMock = vi.mocked(useTheme);
const setTheme = vi.fn();

function mockTheme(theme: string, resolvedTheme = theme) {
  useThemeMock.mockReturnValue({
    theme,
    resolvedTheme,
    setTheme,
    themes: ["light", "dark", "system"],
  } as unknown as ReturnType<typeof useTheme>);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTheme("system", "light");
});

describe("ThemeMenu", () => {
  it("names the current choice, and what system currently resolves to", () => {
    render(<ThemeMenu />);
    expect(screen.getByRole("button", { name: /theme: system \(light\)/i })).toBeInTheDocument();
  });

  it("names a pinned choice without a resolution suffix", () => {
    mockTheme("dark");
    render(<ThemeMenu />);
    expect(screen.getByRole("button", { name: "Theme: Dark" })).toBeInTheDocument();
  });

  it("opens a menu with all three choices", () => {
    render(<ThemeMenu />);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /theme/i }));
    const items = screen.getAllByRole("menuitemradio");
    expect(items.map((item) => item.textContent)).toEqual(["Light", "Dark", "System"]);
  });

  it("marks the active choice as checked", () => {
    mockTheme("light");
    render(<ThemeMenu />);
    fireEvent.click(screen.getByRole("button", { name: /theme/i }));
    expect(screen.getByRole("menuitemradio", { name: "Light" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("menuitemradio", { name: "Dark" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
  });

  it("sets the chosen theme and closes", () => {
    render(<ThemeMenu />);
    fireEvent.click(screen.getByRole("button", { name: /theme/i }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: "Dark" }));

    expect(setTheme).toHaveBeenCalledWith("dark");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("can choose system explicitly — following the OS is a setting, not a fallback", () => {
    mockTheme("dark");
    render(<ThemeMenu />);
    fireEvent.click(screen.getByRole("button", { name: /theme/i }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: "System" }));
    expect(setTheme).toHaveBeenCalledWith("system");
  });

  it("closes on Escape without changing the theme", () => {
    render(<ThemeMenu />);
    fireEvent.click(screen.getByRole("button", { name: /theme/i }));
    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(setTheme).not.toHaveBeenCalled();
  });

  it("closes when a click lands outside it", () => {
    render(
      <div>
        <ThemeMenu />
        <button type="button">elsewhere</button>
      </div>,
    );
    fireEvent.click(screen.getByRole("button", { name: /theme/i }));
    fireEvent.mouseDown(screen.getByRole("button", { name: "elsewhere" }));

    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(setTheme).not.toHaveBeenCalled();
  });

  it("exposes the popup relationship to assistive tech", () => {
    render(<ThemeMenu />);
    const button = screen.getByRole("button", { name: /theme/i });
    expect(button).toHaveAttribute("aria-haspopup", "menu");
    expect(button).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
  });
});

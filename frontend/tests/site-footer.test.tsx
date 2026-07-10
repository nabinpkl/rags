// Compliance gate (§6b/§6c, CLAUDE.md hard constraint): the attribution
// sentence and takedown/contact links must actually render, verbatim.
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SiteFooter } from "@/components/site-footer";
import { ARXIV_ATTRIBUTION, ARXIV_URL, GITHUB_CONTACT_URL, TAKEDOWN_EMAIL } from "@/lib/attribution";

describe("SiteFooter", () => {
  it("renders the arXiv attribution verbatim", () => {
    render(<SiteFooter />);
    expect(screen.getByText(ARXIV_ATTRIBUTION)).toBeInTheDocument();
  });

  it("links a takedown request to the contact email", () => {
    render(<SiteFooter />);
    const link = screen.getByRole("link", { name: /takedown request/i });
    expect(link).toHaveAttribute("href", `mailto:${TAKEDOWN_EMAIL}`);
  });

  it("links 'Report an issue' to the GitHub issues page", () => {
    render(<SiteFooter />);
    const link = screen.getByRole("link", { name: /report an issue/i });
    expect(link).toHaveAttribute("href", GITHUB_CONTACT_URL);
    expect(link.getAttribute("href")).not.toBe("");
  });

  it("links back to arXiv", () => {
    render(<SiteFooter />);
    const link = screen.getByRole("link", { name: /arxiv/i });
    expect(link).toHaveAttribute("href", ARXIV_URL);
  });
});

import { describe, expect, it } from "vitest";

import { licenseOf } from "@/lib/license-label";

describe("licenseOf", () => {
  it("names every CC vintage the corpus holds from one pattern", () => {
    expect(licenseOf("http://creativecommons.org/licenses/by/4.0/")?.name).toBe("CC BY 4.0");
    expect(licenseOf("http://creativecommons.org/licenses/by-sa/4.0/")?.name).toBe("CC BY-SA 4.0");
    expect(licenseOf("http://creativecommons.org/licenses/by-nc-nd/4.0/")?.name).toBe(
      "CC BY-NC-ND 4.0",
    );
    expect(licenseOf("http://creativecommons.org/licenses/by-nc-sa/3.0/")?.name).toBe(
      "CC BY-NC-SA 3.0",
    );
    expect(licenseOf("http://creativecommons.org/publicdomain/zero/1.0/")?.name).toBe("CC0");
    expect(licenseOf("http://creativecommons.org/publicdomain/")?.name).toBe("Public domain");
  });

  it("links the deed over https even though the corpus records http", () => {
    expect(licenseOf("http://creativecommons.org/licenses/by/4.0/")?.href).toBe(
      "https://creativecommons.org/licenses/by/4.0/",
    );
  });

  it("returns nothing for the arXiv default and for a missing licence", () => {
    // The crop rests on fair use rather than on a grant, so there is no
    // notice we owe and nothing to print on 36,560 of 65,503 cards.
    expect(licenseOf("http://arxiv.org/licenses/nonexclusive-distrib/1.0/")).toBeNull();
    expect(licenseOf(null)).toBeNull();
    expect(licenseOf(undefined)).toBeNull();
    expect(licenseOf("")).toBeNull();
  });
});

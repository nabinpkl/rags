import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MethodNotes } from "@/components/benchmarks/method-notes";
import { BENCHMARK } from "@/lib/benchmarks/retrieval-benchmark";

describe("MethodNotes", () => {
  it("states the models and run from the export, not from copy", () => {
    render(<MethodNotes data={BENCHMARK} />);
    expect(screen.getByText(BENCHMARK.rerank_model)).toBeInTheDocument();
    expect(screen.getByText(BENCHMARK.run_id)).toBeInTheDocument();
    expect(screen.getByText(BENCHMARK.local_rerank_run_id)).toBeInTheDocument();
    expect(screen.getByText(`median per query on a ${BENCHMARK.hardware}`)).toBeInTheDocument();
  });
});

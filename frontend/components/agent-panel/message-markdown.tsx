"use client";

import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { arxivAbsUrl } from "@/lib/arxiv-links";

interface MessageMarkdownProps {
  text: string;
  verifiedPaperIds: ReadonlySet<string>;
}

const ARXIV_ID_PATTERN = /\b(\d{4}\.\d{4,5})(v\d+)?\b/g;
const CITATION_SCHEME = "citation:";

/** Rewrites a VERIFIED arXiv id into a markdown link the `a` override below
 * turns into a citation chip. An unverified id is left as plain text —
 * ReactMarkdown never HTML-parses it, so it renders inert by construction,
 * exactly like every other word in the answer (DECISIONS.md 2026-07-08). */
function linkifyVerifiedCitations(text: string, verifiedPaperIds: ReadonlySet<string>): string {
  return text.replace(ARXIV_ID_PATTERN, (match, id: string) =>
    verifiedPaperIds.has(id) ? `[${match}](${CITATION_SCHEME}${id})` : match,
  );
}

const CitationOrInertLink: Components["a"] = ({ href, children }) => {
  if (href?.startsWith(CITATION_SCHEME)) {
    const paperId = href.slice(CITATION_SCHEME.length);
    return (
      <a
        href={arxivAbsUrl(paperId)}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-block rounded border border-machine-accent/40 bg-machine-accent/10 px-1 font-mono text-[10px] text-machine-accent hover:bg-machine-accent/20"
      >
        {children}
      </a>
    );
  }
  // Any other link the answer text happens to contain (e.g. a URL quoted
  // from untrusted, fenced corpus content, §5/§6) renders as plain text —
  // no outbound link askRAG didn't construct itself.
  return <span>{children}</span>;
};

function citationUrlTransform(url: string): string {
  // react-markdown's defaultUrlTransform allow-lists http(s)/irc(s)/mailto/
  // xmpp and drops everything else (including our synthetic scheme) — this
  // is the one, explicit exception, everything else still goes through the
  // library's own safe-URL check.
  return url.startsWith(CITATION_SCHEME) ? url : defaultUrlTransform(url);
}

/** react-markdown + remark-gfm, NO rehype-raw, `skipHtml: true`, NO
 * `dangerouslySetInnerHTML` — hostile HTML in answer text (e.g. a
 * prompt-injection attempt echoed back from fenced, untrusted corpus
 * content, §6) is never parsed as markup, only ever as inert text. This
 * holds by construction: there is no code path in this component capable of
 * turning a string into a DOM element other than react-markdown's own
 * allow-listed tag renderers below. */
export function MessageMarkdown({ text, verifiedPaperIds }: MessageMarkdownProps) {
  return (
    <div className="text-machine-text text-[13.5px] leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        urlTransform={citationUrlTransform}
        components={{ a: CitationOrInertLink }}
      >
        {linkifyVerifiedCitations(text, verifiedPaperIds)}
      </ReactMarkdown>
      {/* §6c: every answer carries this label, unconditionally. */}
      <div className="mt-1 font-mono text-[9.5px] tracking-wide text-machine-muted uppercase">
        AI-generated
      </div>
    </div>
  );
}

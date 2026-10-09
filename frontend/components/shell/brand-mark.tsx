import Image from "next/image";

/** The product's name and mark, at the head of the shell's rail.
 *
 * The geometry is REFERENCED, not redrawn: `app/icon.svg` is the one copy of
 * it and Next already serves it at /icon.svg by the metadata convention. A
 * second copy in JSX would drift the first time the tab icon changed.
 *
 * The tagline used to be a prop because each route brought its own rail and
 * said what that rail was showing. One rail serves both routes now, so the
 * line says what the corpus is and the nav below it says which view.
 */
export function BrandMark() {
  return (
    <>
      <Image src="/icon.svg" alt="" width={26} height={26} className="rounded-[6px]" />
      <span className="min-w-0">
        <b className="font-serif text-ink block text-[17px] leading-none font-bold">
          ask<em className="text-teal-ink not-italic">RAG</em>
        </b>
        <span className="text-muted mt-1 block truncate font-mono text-[9.5px] tracking-[0.1em] uppercase">
          arXiv cs corpus
        </span>
      </span>
    </>
  );
}

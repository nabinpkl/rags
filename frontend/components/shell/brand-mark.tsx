import Image from "next/image";

/** The product's name and mark, wherever a surface has to say what this is.
 *
 * The geometry is REFERENCED, not redrawn: `app/icon.svg` is the one copy of
 * it and Next already serves it at /icon.svg by the metadata convention. A
 * second copy in JSX would drift the first time the tab icon changed.
 *
 * `tagline` is what the surface is showing, which differs by route — the
 * dashboard's rail says which corpus, the catalog says which table.
 */
export function BrandMark({ tagline }: { tagline: string }) {
  return (
    <>
      <Image src="/icon.svg" alt="" width={26} height={26} className="rounded-[6px]" />
      <span className="min-w-0">
        <b className="font-serif text-ink block text-[17px] leading-none font-bold">
          ask<em className="text-teal-ink not-italic">RAG</em>
        </b>
        <span className="text-muted mt-1 block truncate font-mono text-[9.5px] tracking-[0.1em] uppercase">
          {tagline}
        </span>
      </span>
    </>
  );
}

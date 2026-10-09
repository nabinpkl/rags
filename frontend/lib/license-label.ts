/** A paper's licence URL as a name and a deed link, or null.
 *
 * The card shows a crop of the paper (D19). A Creative Commons licence
 * permits that on the condition that the licence is NAMED and linked beside
 * the attribution the card already carries, so this is a compliance
 * requirement rather than a metadata nicety: dropping the label would not
 * degrade the card, it would breach the licence.
 *
 * arXiv's own default licence returns null. It requires no notice from us —
 * the crop rests on fair use, not on a grant — and printing
 * "arXiv nonexclusive-distrib" on 36,560 of 65,503 cards would say nothing a
 * reader of an arXiv index does not already assume.
 */
export type License = { name: string; href: string };

const CC_ZERO = /creativecommons\.org\/publicdomain\/zero/;
const CC_MARK = /creativecommons\.org\/publicdomain/;
// The clause list and the version are both in the path, and both vintages in
// the corpus (3.0 and 4.0) spell them the same way, so one pattern covers
// every CC licence rather than a map that needs a row per combination.
const CC = /creativecommons\.org\/licenses\/([a-z-]+)\/(\d+\.\d+)/;

export function licenseOf(url: string | null | undefined): License | null {
  if (!url) return null;
  const href = url.replace("http://", "https://");
  if (CC_ZERO.test(url)) return { name: "CC0", href };
  const cc = CC.exec(url);
  if (cc) return { name: `CC ${cc[1].toUpperCase()} ${cc[2]}`, href };
  if (CC_MARK.test(url)) return { name: "Public domain", href };
  return null;
}

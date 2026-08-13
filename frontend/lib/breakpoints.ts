/** The two viewport thresholds the shell layout turns on.
 *
 * These MUST stay in step with the Tailwind classes that do the actual
 * layout (`md:` = 768px, `lg:` = 1024px). CSS decides where a panel sits;
 * these queries only tell JS which ARIA semantics that panel should carry —
 * a docked column is a plain region, the same node as a drawer is a modal
 * dialog. There is no way to ask CSS that question, so the numbers live
 * here, named, rather than as bare strings at the call sites.
 */

/** At/above this width the facet rail is a docked column (Tailwind `md:`). */
export const MEDIA_FILTERS_DOCKED = "(min-width: 768px)";

/** At/above this width the agent panel is a docked column (Tailwind `lg:`). */
export const MEDIA_AGENT_DOCKED = "(min-width: 1024px)";

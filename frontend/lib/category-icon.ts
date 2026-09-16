import {
  Bot,
  Brain,
  Code2,
  Cpu,
  Eye,
  FileText,
  type LucideIcon,
  MessageSquareText,
  Network,
  Radio,
  Search,
  ShieldCheck,
  Sigma,
} from "lucide-react";

/** The glyph encodes a paper's FIELD, so a column of papers can be scanned by
 * shape before it is read. Decorative-only icons would make a list slower to
 * read, not faster; an unmapped category falls back to the neutral document.
 *
 * It lives here because two surfaces draw the same column (the dashboard's
 * "what just landed" and the catalog's results) and a second copy would drift
 * the first time a category was added.
 */
export const CATEGORY_ICON: Record<string, LucideIcon> = {
  "cs.CL": MessageSquareText,
  "cs.CV": Eye,
  "cs.LG": Brain,
  "cs.AI": Bot,
  "cs.RO": Cpu,
  "cs.IR": Search,
  "cs.CR": ShieldCheck,
  "cs.SE": Code2,
  "cs.NI": Network,
  "cs.DC": Network,
  "cs.IT": Radio,
  "stat.ML": Sigma,
  "math.OC": Sigma,
};

/** What an unmapped category falls back to. Exported beside the map so both
 * callers reach the icon by property access: the React Compiler refuses to
 * render a component returned from a call it cannot see through. */
export const UNMAPPED_CATEGORY_ICON = FileText;

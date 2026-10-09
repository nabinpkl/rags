import {
  Atom,
  AudioLines,
  Binary,
  BookOpen,
  Bot,
  Brain,
  Calculator,
  ChartLine,
  CircleEllipsis,
  Code2,
  Cpu,
  Database,
  Dna,
  Eye,
  FileText,
  Film,
  Gamepad2,
  Gauge,
  Grid3x3,
  Infinity as InfinityIcon,
  Landmark,
  Library,
  type LucideIcon,
  MessageSquareText,
  Microchip,
  MonitorCog,
  MousePointerClick,
  Network,
  PenTool,
  Radio,
  Regex,
  Search,
  Share2,
  ShieldCheck,
  Sigma,
  SlidersHorizontal,
  Spline,
  SquareFunction,
  Waypoints,
  Workflow,
  Wrench,
} from "lucide-react";

/** The glyph encodes a paper's FIELD, so a column of papers can be scanned by
 * shape before it is read. Decorative-only icons would make a list slower to
 * read, not faster; an unmapped category falls back to the neutral document.
 *
 * It lives here because three surfaces draw the same glyph (the dashboard's
 * "what just landed", the catalog's results and the rail's topic list) and a
 * second copy would drift the first time a category was added.
 *
 * Every cs class has one, so the rail's list of topics has no gaps; the few
 * non-cs codes mapped below are the cross-lists common enough to recognise.
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
  "cs.AR": Microchip,
  "cs.CC": InfinityIcon,
  "cs.CE": Calculator,
  "cs.CG": Spline,
  "cs.CY": Landmark,
  "cs.DB": Database,
  "cs.DL": Library,
  "cs.DM": Grid3x3,
  "cs.DS": Workflow,
  "cs.ET": Atom,
  "cs.FL": Regex,
  "cs.GL": BookOpen,
  "cs.GR": PenTool,
  "cs.GT": Gamepad2,
  "cs.HC": MousePointerClick,
  "cs.LO": Binary,
  "cs.MA": Waypoints,
  "cs.MM": Film,
  "cs.MS": SquareFunction,
  "cs.NA": ChartLine,
  "cs.NE": Dna,
  "cs.OH": CircleEllipsis,
  "cs.OS": MonitorCog,
  "cs.PF": Gauge,
  "cs.PL": Code2,
  "cs.SC": Sigma,
  "cs.SD": AudioLines,
  "cs.SI": Share2,
  "cs.SY": SlidersHorizontal,
  "stat.ML": Sigma,
  "math.OC": Sigma,
};

/** What an unmapped category falls back to. Exported beside the map so both
 * callers reach the icon by property access: the React Compiler refuses to
 * render a component returned from a call it cannot see through. */
export const UNMAPPED_CATEGORY_ICON = FileText;

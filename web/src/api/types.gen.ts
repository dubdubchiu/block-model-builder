/* Generated from schemas/api.schema.json by npm run gen:types. Do not edit. */

export interface BlockModelBuilderAPI {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "BlockError".
 */
export interface BlockError {
  /**
   * The block at fault, or null for a model-level error.
   */
  block: string | null;
  /**
   * What happened and how to fix it.
   */
  message: string;
  /**
   * Inside a subsystem: the inner block's key, instance/inner.
   */
  path?: string | null;
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "BlockInstance".
 */
export interface BlockInstance {
  /**
   * Values for unwired input ports, keyed by port name.
   */
  inline?: {
    [k: string]: number | boolean | string;
  };
  label?: string | null;
  position: Position;
  /**
   * Values that are never wired, e.g. a Constant's value.
   */
  settings?: {
    [k: string]: unknown;
  };
  /**
   * Block type as id@version, e.g. math.add@1.
   */
  spec: string;
  uuid: string;
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "Position".
 */
export interface Position {
  x: number;
  y: number;
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "BlockSpec".
 */
export interface BlockSpec {
  category: string;
  /**
   * False when a period's output depends on later periods (Total, NPV); such blocks can't sit inside a feedback loop.
   */
  causal?: boolean;
  doc: string;
  id: string;
  /**
   * Registered function key. Never code.
   */
  impl: string;
  inputs?: PortSpec[];
  outputs: PortSpec[];
  settings?: SettingSpec[];
  title: string;
  version: number;
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "PortSpec".
 */
export interface PortSpec {
  doc?: string | null;
  /**
   * Default inline value when the port is unwired.
   */
  inline?: number | boolean | string | null;
  name: string;
  required?: boolean;
  /**
   * Port pattern, e.g. number, scalar<integer>, series<date>.
   */
  type: string;
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "SettingSpec".
 */
export interface SettingSpec {
  default?: number | boolean | string | (number | boolean | string)[] | null;
  doc?: string | null;
  name: string;
  /**
   * Allowed values, when the setting is a choice.
   */
  options?: string[] | null;
  type: string;
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "CompositeInput".
 */
export interface CompositeInput {
  name: string;
  /**
   * Inner block inputs this port feeds.
   */
  targets: PortRef[];
  /**
   * Port pattern shown on the subsystem block.
   */
  type?: string;
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "PortRef".
 */
export interface PortRef {
  block: string;
  port: string;
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "CompositeOutput".
 */
export interface CompositeOutput {
  name: string;
  source: PortRef1;
}
/**
 * The inner block output this port exposes.
 */
export interface PortRef1 {
  block: string;
  port: string;
}
/**
 * A subsystem: a reusable group of blocks with its own ports, like a LabVIEW subVI.
 *
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "CompositeSpec".
 */
export interface CompositeSpec {
  blocks: BlockInstance[];
  doc?: string;
  id: string;
  inputs?: CompositeInput[];
  outputs: CompositeOutput[];
  title: string;
  version?: number;
  wires: Wire[];
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "Wire".
 */
export interface Wire {
  from: PortRef;
  to: PortRef;
  uuid: string;
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "EvaluateResponse".
 */
export interface EvaluateResponse {
  /**
   * Engine name and version.
   */
  engine: string;
  errors: BlockError[];
  /**
   * Block uuid (or instance/inner for blocks inside a subsystem), then output port name, then its type and value.
   */
  outputs: {
    [k: string]: {
      [k: string]: PortResult;
    };
  };
  scenario?: string | null;
  timeline: TimelineInfo;
  timing: Timing;
  /**
   * Things to check, such as mismatched units.
   */
  warnings?: BlockError[];
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "PortResult".
 */
export interface PortResult {
  /**
   * Inferred type, e.g. series<currency>.
   */
  type: string;
  unit?: string | null;
  /**
   * A scalar or one value per period (or year); null when not computed or not requested.
   */
  value?: number | boolean | string | number[] | boolean[] | string[] | null;
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "TimelineInfo".
 */
export interface TimelineInfo {
  period_labels: string[];
  /**
   * Fiscal years, the columns of annual values.
   */
  years: number[];
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "Timing".
 */
export interface Timing {
  evaluate_ms: number;
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "LibraryResponse".
 */
export interface LibraryResponse {
  engine: string;
  /**
   * Kinds each pattern word accepts, e.g. number and integer.
   */
  kind_groups: {
    [k: string]: string[];
  };
  specs: BlockSpec[];
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "Model".
 */
export interface Model {
  blocks: BlockInstance[];
  composites?: CompositeSpec[];
  id: string;
  name: string;
  report?: ReportLine[];
  scenarios?: Scenario[];
  schemaVersion: 1;
  timeline: Timeline;
  wires: Wire[];
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "ReportLine".
 */
export interface ReportLine {
  block: string;
  format?: string | null;
  label: string;
  port: string;
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "Scenario".
 */
export interface Scenario {
  id: string;
  name: string;
  /**
   * Changes to top-level blocks' inline values and settings in this scenario.
   */
  overrides?: Override[];
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "Override".
 */
export interface Override {
  block: string;
  inline?: {
    [k: string]: number | boolean | string;
  };
  settings?: {
    [k: string]: unknown;
  };
}
/**
 * This interface was referenced by `BlockModelBuilderAPI`'s JSON-Schema
 * via the `definition` "Timeline".
 */
export interface Timeline {
  fiscal_year_end?: string;
  frequency: "month" | "quarter" | "year";
  periods: number;
  /**
   * First day of period 1; must be the first day of a month.
   */
  start: string;
}

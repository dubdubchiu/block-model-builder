import { Handle, type NodeProps, Position } from "@xyflow/react";
import { formatValue, previewOutput } from "../lib/format";
import type { BlockFlowNode } from "./toFlow";

export function BlockNode({ data, selected }: NodeProps<BlockFlowNode>) {
  const classes = ["bm-node", selected && "bm-node--selected", data.error && "bm-node--error"].filter(Boolean).join(" ");
  return (
    <div className={classes}>
      <div className="bm-node__head">
        <span className="bm-node__title">{data.label ?? data.title}</span>
        <span className="bm-node__id" title={data.uuid}>
          {data.uuid.slice(0, 8)}
        </span>
      </div>
      <div className="bm-node__kind">
        {data.label ? data.title : null}
        {data.composite && <span className="dt-tag">Subsystem</span>}
        {data.source &&
          (data.source.illustrative ? (
            <span className="dt-tag" title="Illustrative figure, not real data">
              Sample
            </span>
          ) : (
            <span className="dt-tag dt-tag--done" title={data.source.text}>
              Sourced
            </span>
          ))}
      </div>

      <div className="bm-node__ports">
        {visibleInputs(data).map((port) => {
          const wired = data.wiredInputs.includes(port.name);
          const inline = data.inline[port.name] ?? port.inline;
          return (
            <div key={port.name} className="bm-port bm-port--in">
              <Handle type="target" position={Position.Left} id={port.name} isConnectable={!data.readOnly} />
              <span className="bm-port__name">{port.name}</span>
              <span className="bm-port__type">{port.type}</span>
              {!wired && inline != null && (
                <span className="bm-port__inline" title="Inline value (input not wired)">
                  = {typeof inline === "string" ? inline : formatValue(inline)}
                </span>
              )}
            </div>
          );
        })}
        {data.outputs.map((port) => (
          <div key={port.name} className="bm-port bm-port--out">
            <span className="bm-port__type">{outputType(data, port.name, port.type)}</span>
            <span className="bm-port__name">{port.name}</span>
            <Handle type="source" position={Position.Right} id={port.name} isConnectable={!data.readOnly} />
          </div>
        ))}
      </div>

      {data.warnings && !data.error && (
        <div className="bm-node__warning" title={data.warnings.join(" ")}>
          <span className="dt-tag dt-tag--caution">Check units</span>
        </div>
      )}
      {data.error ? (
        <div className="bm-node__error">
          <span className="dt-tag dt-tag--danger">Error</span>
          <p>{data.error}</p>
        </div>
      ) : (
        data.outputs.map((port) => {
          const value = data.results?.[port.name]?.value;
          return value != null ? (
            <div key={port.name} className="bm-node__preview" data-testid={`preview-${data.uuid}-${port.name}`}>
              {data.outputs.length > 1 && <span className="bm-node__preview-port">{port.name} </span>}
              {previewOutput(value)}
            </div>
          ) : null;
        })
      )}
    </div>
  );
}

/** The inferred type and unit after evaluation; the spec's pattern before. */
function outputType(data: BlockFlowNode["data"], port: string, pattern: string): string {
  const result = data.results?.[port];
  if (!result) return pattern;
  return result.unit ? `${result.type} ${result.unit}` : result.type;
}

/** Optional inputs that are unwired and unset are hidden, except the first one as a free slot (Sum's in1..in8). */
function visibleInputs(data: BlockFlowNode["data"]) {
  let freeShown = false;
  return data.inputs.filter((p) => {
    if (p.required !== false || data.wiredInputs.includes(p.name) || data.inline[p.name] != null) return true;
    if (freeShown) return false;
    freeShown = true;
    return true;
  });
}

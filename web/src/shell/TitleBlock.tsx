import { APP, BUILD } from "../config";

function Cell({ k, v, mono, kind }: { k: string; v: string; mono?: boolean; kind?: "name" | "status" }) {
  return (
    <div className={kind ? `dt-titleblock__cell dt-titleblock__cell--${kind}` : "dt-titleblock__cell"}>
      <span className="dt-titleblock__k">{k}</span>
      <span className={mono ? "dt-titleblock__v dt-titleblock__v--mono" : "dt-titleblock__v"}>{v}</span>
    </div>
  );
}

export function TitleBlock({ data = APP.data }: { data?: string }) {
  return (
    <div className="dt-titleblock" aria-label="Title block">
      <Cell k="Name" v={APP.name} kind="name" />
      <Cell k="Rev" v={APP.rev} mono />
      <Cell k="Date" v={BUILD.date} mono />
      <Cell k="Status" v={APP.status} kind="status" />
      <Cell k="Owner" v={APP.owner} />
      <Cell k="Data" v={data} />
      <Cell k="Build" v={BUILD.hash} mono />
    </div>
  );
}

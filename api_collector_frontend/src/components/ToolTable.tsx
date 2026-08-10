// src/components/ToolTable.tsx
import React from "react";

interface ToolParameter {
  name: string;
  type: string;
  required: boolean;
  description?: string | null;
  default?: string | null;
}

interface ToolDescription {
  name: string;
  description: string;
  method?: string | null;
  path?: string | null;
  tags: string[];
  parameters: ToolParameter[];
  metadata: Record<string, any>;
}

interface Props {
  tools: ToolDescription[];
}

export const ToolTable: React.FC<Props> = ({ tools }) => {
  if (!tools.length) return null;

  return (
    <div className="border border-slate-800 rounded-xl overflow-hidden text-xs bg-slate-950/80">
      <div className="max-h-64 overflow-auto">
        <table className="w-full border-collapse">
          <thead className="bg-slate-950 sticky top-0 z-10">
            <tr className="text-[11px] text-slate-400 text-left">
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium w-20">Method</th>
              <th className="px-3 py-2 font-medium w-64">Path</th>
              <th className="px-3 py-2 font-medium w-40">Tags</th>
              <th className="px-3 py-2 font-medium">Parameters</th>
            </tr>
          </thead>
          <tbody>
            {tools.map((tool, idx) => (
              <tr
                key={tool.name}
                className={`border-t border-slate-800 hover:bg-slate-900/80 transition ${
                  idx % 2 === 0 ? "bg-slate-950/70" : "bg-slate-950/60"
                }`}
              >
                <td className="px-3 py-2 align-top">
                  <div className="font-semibold text-slate-50 truncate max-w-[220px]">
                    {tool.name}
                  </div>
                  {tool.description && (
                    <div className="text-[11px] text-slate-400 mt-0.5 max-w-[260px]">
                      {tool.description}
                    </div>
                  )}
                </td>
                <td className="px-3 py-2 align-top text-slate-100">
                  {tool.method || "—"}
                </td>
                <td className="px-3 py-2 align-top text-slate-100">
                  {tool.path || "—"}
                </td>
                <td className="px-3 py-2 align-top text-slate-100">
                  {tool.tags && tool.tags.length > 0 ? (
                    <div className="flex flex-wrap gap-1 max-w-[180px]">
                      {tool.tags.map((t) => (
                        <span
                          key={t}
                          className="inline-flex px-2 py-[2px] rounded-full bg-slate-800 text-[10px] text-slate-100 border border-slate-700"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="px-3 py-2 align-top text-slate-100">
                  {tool.parameters && tool.parameters.length > 0 ? (
                    <div className="flex flex-col gap-1 max-w-[280px]">
                      {tool.parameters.map((p) => (
                        <div key={p.name} className="flex gap-2">
                          <span className="font-mono text-[10px] text-slate-100">
                            {p.name}
                            {p.required ? "*" : ""}:
                          </span>
                          <span className="text-[10px] text-slate-400">
                            {p.type}
                            {p.description ? ` — ${p.description}` : ""}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

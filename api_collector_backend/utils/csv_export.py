# api_collector_backend/utils/csv_export.py
from __future__ import annotations
from typing import List
import csv
import io

from ..models import ToolDescription


def tools_to_csv(tools: List[ToolDescription]) -> str:
    """
    Serialize tools into a simple CSV:
    name,description,method,path,tags,parameters_json
    """
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["name", "description", "method", "path", "tags", "parameters_json"])
    for t in tools:
        writer.writerow(
            [
                t.name,
                t.description.replace("\n", " "),
                t.method or "",
                t.path or "",
                "|".join(t.tags),
                [p.model_dump() for p in t.parameters],
            ]
        )
    return buf.getvalue()

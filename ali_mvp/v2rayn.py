import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class V2RayNNode:
    index_id: str
    remarks: str
    address: str
    port: int
    password: str
    method: str
    subid: str
    sort_index: int


@dataclass(frozen=True)
class V2RayNSource:
    root: Path
    db_path: Path
    base_config_path: Path
    xray_path: Path
    asset_dir: Path
    nodes: list[V2RayNNode]


def load_v2rayn_source(root: Path) -> V2RayNSource:
    root = Path(root)
    db_path = root / "guiConfigs" / "guiNDB.db"
    base_config_path = root / "binConfigs" / "config.json"
    xray_path = root / "bin" / "xray.exe"
    asset_dir = root / "bin"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT rowid, IndexId, ConfigType, Subid, IsSub, Remarks, Address, Port, Password, ProtoExtra, Id
        FROM ProfileItem
        ORDER BY rowid
        """
    ).fetchall()
    conn.close()

    nodes: list[V2RayNNode] = []
    for row in rows:
        try:
            proto_extra = json.loads(row["ProtoExtra"] or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(proto_extra, dict):
            continue
        method = str(proto_extra.get("SsMethod") or "")
        if int(row["ConfigType"] or 0) != 3 or not row["Password"] or not method:
            continue
        nodes.append(
            V2RayNNode(
                index_id=str(row["IndexId"]),
                remarks=str(row["Remarks"] or ""),
                address=str(row["Address"] or ""),
                port=int(row["Port"] or 0),
                password=str(row["Password"] or ""),
                method=method,
                subid=str(row["Subid"] or ""),
                sort_index=int(row["rowid"]),
            )
        )

    return V2RayNSource(
        root=root,
        db_path=db_path,
        base_config_path=base_config_path,
        xray_path=xray_path,
        asset_dir=asset_dir,
        nodes=nodes,
    )

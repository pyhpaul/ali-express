import sqlite3

from ali_mvp.v2rayn import load_v2rayn_source


def test_load_v2rayn_source_reads_profile_item_order_and_ss_method(tmp_path):
    root = tmp_path / "v2rayN"
    db_path = root / "guiConfigs" / "guiNDB.db"
    config_path = root / "binConfigs" / "config.json"
    xray_path = root / "bin" / "xray.exe"
    db_path.parent.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)
    xray_path.parent.mkdir(parents=True)
    config_path.write_text(
        '{"inbounds":[{"port":10808}],"outbounds":[{"settings":{"servers":[]}}]}',
        encoding="utf-8",
    )
    xray_path.write_text("", encoding="utf-8")

    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE ProfileItem (IndexId varchar PRIMARY KEY, ConfigType INTEGER, Subid varchar, IsSub INTEGER, Remarks varchar, Address varchar, Port INTEGER, Password varchar, ProtoExtra varchar, Id varchar)"
    )
    conn.execute(
        "INSERT INTO ProfileItem VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("node-a", 3, "sub-1", 1, "HK A", "1.1.1.1", 1111, "secret-a", '{"SsMethod":"aes-256-gcm"}', ""),
    )
    conn.execute(
        "INSERT INTO ProfileItem VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("node-b", 3, "sub-1", 1, "JP B", "2.2.2.2", 2222, "secret-b", '{"SsMethod":"2022-blake3-aes-256-gcm"}', ""),
    )
    conn.commit()
    conn.close()

    source = load_v2rayn_source(root)

    assert [node.index_id for node in source.nodes] == ["node-a", "node-b"]
    assert source.nodes[0].method == "aes-256-gcm"
    assert source.nodes[1].method == "2022-blake3-aes-256-gcm"
    assert source.xray_path == xray_path


def test_load_v2rayn_source_skips_non_ss_rows(tmp_path):
    root = tmp_path / "v2rayN"
    db_path = root / "guiConfigs" / "guiNDB.db"
    config_path = root / "binConfigs" / "config.json"
    xray_path = root / "bin" / "xray.exe"
    db_path.parent.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)
    xray_path.parent.mkdir(parents=True)
    config_path.write_text(
        '{"inbounds":[{"port":10808}],"outbounds":[{"settings":{"servers":[]}}]}',
        encoding="utf-8",
    )
    xray_path.write_text("", encoding="utf-8")

    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE ProfileItem (IndexId varchar PRIMARY KEY, ConfigType INTEGER, Subid varchar, IsSub INTEGER, Remarks varchar, Address varchar, Port INTEGER, Password varchar, ProtoExtra varchar, Id varchar)"
    )
    conn.execute(
        "INSERT INTO ProfileItem VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("node-http", 5, "sub-1", 1, "HTTP", "3.3.3.3", 3333, "", "{}", ""),
    )
    conn.commit()
    conn.close()

    assert load_v2rayn_source(root).nodes == []

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
    assert source.db_path == db_path
    assert source.base_config_path == config_path
    assert source.xray_path == xray_path
    assert source.asset_dir == root / "bin"


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


def test_load_v2rayn_source_skips_row_with_invalid_proto_extra_json(tmp_path):
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
        ("node-bad-json", 3, "sub-1", 1, "Bad JSON", "4.4.4.4", 4444, "secret", "not-json", ""),
    )
    conn.execute(
        "INSERT INTO ProfileItem VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("node-good", 3, "sub-1", 1, "Good", "5.5.5.5", 5555, "secret-good", '{"SsMethod":"aes-128-gcm"}', ""),
    )
    conn.commit()
    conn.close()

    source = load_v2rayn_source(root)

    assert [node.index_id for node in source.nodes] == ["node-good"]


def test_load_v2rayn_source_skips_row_with_non_object_proto_extra(tmp_path):
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
        ("node-null", 3, "sub-1", 1, "Null", "6.6.6.6", 6666, "secret-null", "null", ""),
    )
    conn.execute(
        "INSERT INTO ProfileItem VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("node-list", 3, "sub-1", 1, "List", "7.7.7.7", 7777, "secret-list", "[]", ""),
    )
    conn.execute(
        "INSERT INTO ProfileItem VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("node-good", 3, "sub-1", 1, "Good", "8.8.8.8", 8888, "secret-good", '{"SsMethod":"chacha20-ietf-poly1305"}', ""),
    )
    conn.commit()
    conn.close()

    source = load_v2rayn_source(root)

    assert [node.index_id for node in source.nodes] == ["node-good"]

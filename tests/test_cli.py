import argparse
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import pytest

from ali_mvp.cli import build_output_dir, build_parser, run_postprocess, run_resume, run_scrape
from ali_mvp.filtering import FilterGroup


def test_scrape_parser_defaults_pages_to_none():
    parser = build_parser()
    args = parser.parse_args(["scrape", "--keyword", "women dress"])

    assert args.pages is None


def test_scrape_parser_accepts_browser_profile_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "scrape",
            "--keyword",
            "women dress",
            "--max-items",
            "20",
            "--user-data-dir",
            ".browser-profile",
            "--port",
            "9333",
        ]
    )

    assert args.keyword == "women dress"
    assert args.user_data_dir == ".browser-profile"
    assert args.port == 9333
    assert args.browser_hardening == "minimal"


def test_scrape_parser_accepts_explicit_browser_hardening_off():
    parser = build_parser()

    args = parser.parse_args(["scrape", "--keyword", "women dress", "--browser-hardening", "off"])

    assert args.browser_hardening == "off"


def test_scrape_parser_accepts_pages_option():
    parser = build_parser()
    args = parser.parse_args(["scrape", "--keyword", "women dress", "--pages", "3"])

    assert args.pages == 3


def test_scrape_parser_accepts_enrich_detail_option():
    parser = build_parser()
    args = parser.parse_args(["scrape", "--keyword", "women dress", "--enrich-detail"])

    assert args.enrich_detail is True


def test_scrape_parser_accepts_blacklist_file_and_repeatable_reject_keyword():
    parser = build_parser()

    args = parser.parse_args(
        [
            "scrape",
            "--keyword",
            "home appliance accessories",
            "--blacklist-file",
            "rules/product_blacklist.json",
            "--reject-keyword",
            "sensor",
            "--reject-keyword",
            "relay",
        ]
    )

    assert args.blacklist_file == "rules/product_blacklist.json"
    assert args.reject_keyword == ["sensor", "relay"]


def test_scrape_parser_rejects_invalid_browser_hardening_value():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["scrape", "--keyword", "women dress", "--browser-hardening", "aggressive"])


def test_parser_accepts_postprocess_run_dir_and_default_browser_hardening():
    parser = build_parser()

    scrape_args = parser.parse_args(["scrape", "--keyword", "women dress"])
    post_args = parser.parse_args(["postprocess", "--run-dir", "data/run-1"])

    assert scrape_args.browser_hardening == "minimal"
    assert scrape_args.func is run_scrape
    assert post_args.func is run_postprocess
    assert post_args.run_dir == "data/run-1"


def test_postprocess_parser_accepts_translator_options():
    parser = build_parser()

    args = parser.parse_args(
        [
            "postprocess",
            "--run-dir",
            "data/run-1",
            "--translator",
            "mymemory",
            "--translator-email",
            "ops@example.com",
        ]
    )

    assert args.run_dir == "data/run-1"
    assert args.translator == "mymemory"
    assert args.translator_email == "ops@example.com"


def test_parser_binds_handlers_for_scrape_and_postprocess():
    parser = build_parser()

    scrape_args = parser.parse_args(["scrape", "--keyword", "women dress"])
    post_args = parser.parse_args(["postprocess", "--run-dir", "data/run-1"])

    assert scrape_args.func is run_scrape
    assert post_args.func is run_postprocess


def test_resume_parser_accepts_run_dir_and_details_only():
    parser = build_parser()

    args = parser.parse_args(["resume", "--run-dir", "data/run-1", "--details-only"])

    assert args.run_dir == "data/run-1"
    assert args.details_only is True
    assert args.func is run_resume


def test_run_resume_delegates_to_scrape_runner(monkeypatch, tmp_path, capsys):
    from ali_mvp import cli
    from ali_mvp.scrape_runner import RunResult

    seen: dict[str, object] = {}

    def fake_resume_scrape(run_dir: Path, *, details_only: bool):
        seen["run_dir"] = run_dir
        seen["details_only"] = details_only
        return RunResult(exit_code=0, accepted_count=7, blocked=False)

    monkeypatch.setattr("ali_mvp.scrape_runner.resume_scrape", fake_resume_scrape)

    args = argparse.Namespace(run_dir=str(tmp_path / "run-1"), details_only=True)

    code = cli.run_resume(args)
    output = capsys.readouterr().out

    assert code == 0
    assert seen == {
        "run_dir": tmp_path / "run-1",
        "details_only": True,
    }
    assert f"Resumed run: {tmp_path / 'run-1'}" in output
    assert "Accepted products: 7" in output


def test_run_postprocess_writes_review_zh_and_html(monkeypatch, tmp_path):
    from ali_mvp import cli
    from ali_mvp.output import read_csv_rows

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "products.csv").write_text(
        "source_type,source_value,title,price,sold_count,rating,review_count,product_url,search_card_url,image_url,entry_type,is_promoted,promo_channel,promotion_text,promo_landing_url,shop_name,shipping_text,detail_rating,detail_review_count,breadcrumb,attributes_text,description_text,detail_status,scraped_at\n"
        "keyword,home appliance accessories,Shock pad,$1,0,0,0,https://example.test/item/1,https://example.test/card/1,https://example.test/img.jpg,item_card,False,,, ,Store A,Free shipping,0,0,,\"{\"\"Type\"\":\"\"Pad\"\"}\",Accessory,,2026-05-11T00:00:00Z\n",
        encoding="utf-8-sig",
    )
    (run_dir / "products_filter_audit.csv").write_text(
        "source_type,source_value,title,product_url,filter_decision,filter_stage,reject_groups,reject_terms,reject_fields,warning_groups,warning_terms,warning_fields\n"
        "keyword,home appliance accessories,Shock pad,https://example.test/item/1,accepted,accepted,,,,,,\n",
        encoding="utf-8-sig",
    )

    args = argparse.Namespace(run_dir=str(run_dir), translator="identity", translator_email="")

    code = cli.run_postprocess(args)

    assert code == 0
    assert (run_dir / "products_review.csv").exists()
    assert (run_dir / "products_zh.csv").exists()
    assert (run_dir / "products_filter_audit_zh.csv").exists()
    assert (run_dir / "review_only.csv").exists()
    assert (run_dir / "products_report.html").exists()
    assert (run_dir / "translation_cache.json").exists()
    assert len(read_csv_rows(run_dir / "products_review.csv")) == 1
    assert len(read_csv_rows(run_dir / "products_zh.csv")) == 1
    assert len(read_csv_rows(run_dir / "products_filter_audit_zh.csv")) == 1
    assert len(read_csv_rows(run_dir / "review_only.csv")) == 1


def test_run_postprocess_builds_translator_and_passes_it_through(monkeypatch, tmp_path):
    from ali_mvp import cli

    run_dir = tmp_path / "run"
    built: dict[str, object] = {}

    def fake_build_translator(provider: str, *, email: str):
        built["provider"] = provider
        built["email"] = email
        return lambda text: f"ZH::{text}"

    def fake_run_postprocess_for_dir(path: Path, *, translator, translation_cache_namespace):
        built["run_dir"] = path
        built["translated"] = translator("Shock pad")
        built["translation_cache_namespace"] = translation_cache_namespace

    monkeypatch.setattr("ali_mvp.translation.build_translator", fake_build_translator)
    monkeypatch.setattr("ali_mvp.postprocess.run_postprocess_for_dir", fake_run_postprocess_for_dir)

    args = argparse.Namespace(run_dir=str(run_dir), translator="mymemory", translator_email="ops@example.com")

    code = cli.run_postprocess(args)

    assert code == 0
    assert built == {
        "provider": "mymemory",
        "email": "ops@example.com",
        "run_dir": run_dir,
        "translated": "ZH::Shock pad",
        "translation_cache_namespace": "mymemory",
    }


def test_run_scrape_rejects_non_positive_pages():
    from ali_mvp import cli

    args = argparse.Namespace(
        keyword="women dress",
        url=None,
        category_url=None,
        max_items=20,
        output_dir="data",
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        pages=0,
    )

    with pytest.raises(SystemExit, match="--pages must be greater than 0"):
        cli.run_scrape(args)


def test_scrape_parser_rejects_removed_detail_rating_flags():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["scrape", "--keyword", "women dress", "--enrich-detail-rating"])

    with pytest.raises(SystemExit):
        parser.parse_args(["scrape", "--keyword", "women dress", "--detail-limit", "3"])


def test_run_scrape_builds_manifest_and_delegates_to_runner(monkeypatch, tmp_path, capsys):
    from ali_mvp import cli

    fixed_now = datetime.fromisoformat("2026-05-11T08:00:00+00:00")
    args = argparse.Namespace(
        keyword="home appliance accessories",
        url=None,
        category_url=None,
        max_items=20,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        pages=1,
        blacklist_file=None,
        reject_keyword=["battery"],
        browser_hardening="minimal",
    )

    class FakeDateTime:
        @classmethod
        def now(cls):
            return fixed_now

    seen: dict[str, object] = {}

    def fake_run_new_scrape(*, manifest, groups, run_dir):
        seen["manifest"] = manifest
        seen["groups"] = groups
        seen["run_dir"] = run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        for name in ("products.csv", "products_filter_audit.csv", "products_review.csv", "category_rank.csv"):
            (run_dir / name).write_text("", encoding="utf-8")
        return cli.scrape_runner.RunResult(exit_code=0, accepted_count=4, blocked=False)

    monkeypatch.setattr(cli, "datetime", FakeDateTime)
    monkeypatch.setattr(
        cli,
        "load_filter_groups",
        lambda path, keywords: [FilterGroup(name="cli_extra", post_reject_terms=("battery",))],
    )
    monkeypatch.setattr(cli.scrape_runner, "run_new_scrape", fake_run_new_scrape)

    code = cli.run_scrape(args)
    output = capsys.readouterr().out

    assert code == 0
    assert seen["manifest"].source_type == "keyword"
    assert seen["manifest"].source_value == "home appliance accessories"
    assert seen["manifest"].url == "https://www.aliexpress.com/wholesale?SearchText=home+appliance+accessories"
    assert seen["manifest"].created_at == "2026-05-11T08:00:00+00:00"
    assert seen["manifest"].browser_hardening == "minimal"
    assert seen["manifest"].reject_keyword == ["battery"]
    assert seen["groups"] == [FilterGroup(name="cli_extra", post_reject_terms=("battery",))]
    assert seen["run_dir"] == build_output_dir(
        Path(tmp_path),
        source_type="keyword",
        source_value="home appliance accessories",
        run_at=fixed_now,
    )
    assert "Accepted products: 4" in output
    assert f"Wrote: {seen['run_dir'] / 'products.csv'}" in output


def test_run_scrape_passes_browser_hardening_and_category_source_into_runner_manifest(monkeypatch, tmp_path):
    from ali_mvp import cli

    fixed_now = datetime.fromisoformat("2026-05-11T08:00:00+00:00")
    category_url = "https://www.aliexpress.com/category/100003109/women-clothing.html"
    args = argparse.Namespace(
        keyword=None,
        url=None,
        category_url=category_url,
        max_items=1,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        pages=1,
        blacklist_file=None,
        reject_keyword=[],
        browser_hardening="minimal",
    )

    class FakeDateTime:
        @classmethod
        def now(cls):
            return fixed_now

    seen: dict[str, object] = {}

    def fake_run_new_scrape(*, manifest, groups, run_dir):
        seen["manifest"] = manifest
        seen["run_dir"] = run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        for name in ("products.csv", "products_filter_audit.csv", "products_review.csv", "category_rank.csv"):
            (run_dir / name).write_text("", encoding="utf-8")
        return cli.scrape_runner.RunResult(exit_code=0, accepted_count=1, blocked=False)

    monkeypatch.setattr(cli, "datetime", FakeDateTime)
    monkeypatch.setattr(cli, "load_filter_groups", lambda path, keywords: [])
    monkeypatch.setattr(cli.scrape_runner, "run_new_scrape", fake_run_new_scrape)

    cli.run_scrape(args)

    assert seen["manifest"].browser_hardening == "minimal"
    assert seen["manifest"].source_type == "category"
    assert seen["manifest"].source_value == category_url
    assert seen["manifest"].url == category_url
    assert seen["run_dir"] == build_output_dir(
        Path(tmp_path),
        source_type="category",
        source_value=category_url,
        run_at=fixed_now,
    )


def test_run_scrape_run_dir_manifest_can_be_consumed_by_run_resume(monkeypatch, tmp_path, capsys):
    from ali_mvp import cli
    from ali_mvp.run_state import RunState, RunStateStore

    fixed_now = datetime.fromisoformat("2026-05-11T08:00:00+00:00")
    args = argparse.Namespace(
        keyword="women dress",
        url=None,
        category_url=None,
        max_items=20,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=True,
        pages=None,
        blacklist_file=None,
        reject_keyword=[],
        browser_hardening="minimal",
    )

    class FakeDateTime:
        @classmethod
        def now(cls):
            return fixed_now

    seen: dict[str, object] = {}

    def fake_run_new_scrape(*, manifest, groups, run_dir):
        seen["run_dir"] = run_dir
        store = RunStateStore(run_dir)
        blocked_state = RunState(
            status="blocked",
            current_listing_page=1,
            pending_detail_queue=[
                {
                    "url": "https://www.aliexpress.com/item/1001.html",
                    "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
                }
            ],
            last_block_reason="captcha_blocked",
            last_blocked_url="https://www.aliexpress.com/item/1001.html",
        )
        store.save_manifest(manifest)
        store.save_state(blocked_state)
        store.save_summary(blocked_state)
        for name in ("products.csv", "products_filter_audit.csv", "products_review.csv", "category_rank.csv"):
            (run_dir / name).write_text("", encoding="utf-8")
        return cli.scrape_runner.RunResult(exit_code=3, accepted_count=0, blocked=True)

    def fake_resume_scrape(run_dir: Path, *, details_only: bool):
        store = RunStateStore(run_dir)
        seen["resume_manifest"] = store.load_manifest()
        seen["resume_state"] = store.load_state()
        seen["resume_details_only"] = details_only
        return cli.scrape_runner.RunResult(exit_code=0, accepted_count=1, blocked=False)

    monkeypatch.setattr(cli, "datetime", FakeDateTime)
    monkeypatch.setattr(cli, "load_filter_groups", lambda path, keywords: [])
    monkeypatch.setattr(cli.scrape_runner, "run_new_scrape", fake_run_new_scrape)
    monkeypatch.setattr(cli.scrape_runner, "resume_scrape", fake_resume_scrape)

    scrape_code = cli.run_scrape(args)
    scrape_output = capsys.readouterr().out

    resume_code = cli.run_resume(argparse.Namespace(run_dir=str(seen["run_dir"]), details_only=True))
    resume_output = capsys.readouterr().out

    assert scrape_code == 3
    assert "Accepted products: 0" in scrape_output
    assert seen["resume_manifest"].source_type == "keyword"
    assert seen["resume_manifest"].source_value == "women dress"
    assert seen["resume_manifest"].created_at == "2026-05-11T08:00:00+00:00"
    assert seen["resume_state"].status == "blocked"
    assert seen["resume_state"].pending_detail_queue == [
        {
            "url": "https://www.aliexpress.com/item/1001.html",
            "resolvedProductUrl": "https://www.aliexpress.com/item/1001.html",
        }
    ]
    assert seen["resume_details_only"] is True
    assert resume_code == 0
    assert f"Resumed run: {seen['run_dir']}" in resume_output
    assert "Accepted products: 1" in resume_output


def test_run_scrape_with_blacklist_reports_full_processed_counts_when_final_page_accepts_are_truncated(
    monkeypatch,
    tmp_path,
    capsys,
):
    from ali_mvp import cli

    fixed_now = datetime.fromisoformat("2026-05-11T08:00:00+00:00")
    args = argparse.Namespace(
        keyword="home appliance accessories",
        url=None,
        category_url=None,
        max_items=2,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=True,
        pages=None,
        blacklist_file="rules/product_blacklist.json",
        reject_keyword=[],
        browser_hardening="minimal",
    )

    class FakeDateTime:
        @classmethod
        def now(cls):
            return fixed_now

    def fake_run_new_scrape(*, manifest, groups, run_dir):
        run_dir.mkdir(parents=True, exist_ok=True)
        for name in ("products.csv", "products_filter_audit.csv", "products_review.csv", "category_rank.csv"):
            (run_dir / name).write_text("", encoding="utf-8")
        return cli.scrape_runner.RunResult(exit_code=0, accepted_count=2, blocked=False)

    monkeypatch.setattr(cli, "datetime", FakeDateTime)
    monkeypatch.setattr(cli, "load_filter_groups", lambda path, keywords: [])
    monkeypatch.setattr(cli.scrape_runner, "run_new_scrape", fake_run_new_scrape)

    code = cli.run_scrape(args)
    output = capsys.readouterr().out

    assert code == 0
    assert "Accepted products: 2" in output
    run_dir = build_output_dir(
        Path(tmp_path),
        source_type="keyword",
        source_value="home appliance accessories",
        run_at=fixed_now,
    )
    assert f"Wrote: {run_dir / 'products.csv'}" in output
    assert f"Wrote: {run_dir / 'products_filter_audit.csv'}" in output


def test_run_scrape_returns_runner_exit_code_when_no_products_are_accepted(monkeypatch, tmp_path, capsys):
    from ali_mvp import cli

    fixed_now = datetime.fromisoformat("2026-05-11T08:00:00+00:00")
    args = argparse.Namespace(
        keyword="home appliance accessories",
        url=None,
        category_url=None,
        max_items=2,
        output_dir=str(tmp_path),
        user_data_dir=".browser-profile",
        port=9333,
        enrich_detail=False,
        pages=1,
        blacklist_file="rules/product_blacklist.json",
        reject_keyword=[],
        browser_hardening="minimal",
    )

    class FakeDateTime:
        @classmethod
        def now(cls):
            return fixed_now

    def fake_run_new_scrape(*, manifest, groups, run_dir):
        run_dir.mkdir(parents=True, exist_ok=True)
        for name in ("products.csv", "products_filter_audit.csv", "products_review.csv", "category_rank.csv"):
            (run_dir / name).write_text("", encoding="utf-8")
        return cli.scrape_runner.RunResult(exit_code=2, accepted_count=0, blocked=False)

    monkeypatch.setattr(cli, "datetime", FakeDateTime)
    monkeypatch.setattr(cli, "load_filter_groups", lambda path, keywords: [])
    monkeypatch.setattr(cli.scrape_runner, "run_new_scrape", fake_run_new_scrape)

    code = cli.run_scrape(args)
    output = capsys.readouterr().out

    assert code == 2
    assert "Accepted products: 0" in output
    assert "No accepted products extracted." in output


def test_build_output_dir_groups_keyword_runs_by_slug_and_timestamp():
    run_at = datetime(2026, 5, 8, 22, 45, 30)

    path = build_output_dir(Path("data"), source_type="keyword", source_value="women dress", run_at=run_at)

    assert path == Path("data") / "women-dress" / "20260508_224530"


def test_build_output_dir_groups_url_runs_under_url_slug():
    run_at = datetime(2026, 5, 8, 22, 45, 30)

    path = build_output_dir(Path("data"), source_type="url", source_value="https://example.test/x", run_at=run_at)

    assert path == Path("data") / "url" / "20260508_224530"


def test_scrape_parser_accepts_category_url_source():
    parser = build_parser()
    args = parser.parse_args(
        [
            "scrape",
            "--category-url",
            "https://www.aliexpress.com/category/100003109/women-clothing.html",
        ]
    )

    assert args.category_url == "https://www.aliexpress.com/category/100003109/women-clothing.html"


def test_build_output_dir_groups_category_url_by_category_slug():
    run_at = datetime(2026, 5, 8, 22, 45, 30)

    path = build_output_dir(
        Path("data"),
        source_type="category",
        source_value="https://www.aliexpress.com/category/100003109/women-clothing.html",
        run_at=run_at,
    )

    assert path == Path("data") / "category-women-clothing" / "20260508_224530"


def test_build_output_dir_falls_back_for_category_url_without_slug():
    run_at = datetime(2026, 5, 8, 22, 45, 30)

    path = build_output_dir(
        Path("data"),
        source_type="category",
        source_value="https://www.aliexpress.com/category/",
        run_at=run_at,
    )

    assert path == Path("data") / "category" / "20260508_224530"

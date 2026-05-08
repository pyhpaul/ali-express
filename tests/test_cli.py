from ali_mvp.cli import build_parser


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


def test_scrape_parser_accepts_detail_rating_enrichment_options():
    parser = build_parser()
    args = parser.parse_args(
        [
            "scrape",
            "--keyword",
            "women dress",
            "--enrich-detail-rating",
            "--detail-limit",
            "3",
        ]
    )

    assert args.enrich_detail_rating is True
    assert args.detail_limit == 3

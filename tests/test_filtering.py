import json
from pathlib import Path

from ali_mvp.filtering import FilterGroup, filter_products, load_filter_groups, prefilter_listing_products
from ali_mvp.scoring import ProductRecord


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "filtering"


def _load_fixture(name: str) -> list[dict[str, object]]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _make_product(raw: dict[str, object]) -> ProductRecord:
    return ProductRecord(
        source_type="keyword",
        source_value="home appliance accessories",
        title=str(raw["title"]),
        price="$1.00",
        sold_count=0,
        rating=0.0,
        review_count=0,
        product_url=str(raw["product_url"]),
        search_card_url=str(raw["product_url"]),
        image_url="https://example.test/item.jpg",
        entry_type="item_card",
        is_promoted=False,
        promo_channel="",
        promotion_text="",
        promo_landing_url="",
        shop_name="",
        shipping_text="",
        detail_rating=0.0,
        detail_review_count=0,
        breadcrumb=str(raw.get("breadcrumb", "")),
        attributes_text=str(raw.get("attributes_text", "")),
        description_text=str(raw.get("description_text", "")),
        scraped_at="2026-05-09T00:00:00Z",
    )


def make_product(
    *,
    title: str,
    attributes_text: str = "",
    breadcrumb: str = "",
    description_text: str = "",
) -> ProductRecord:
    return ProductRecord(
        source_type="keyword",
        source_value="home appliance accessories",
        title=title,
        price="$1.00",
        sold_count=0,
        rating=0.0,
        review_count=0,
        product_url="https://example.test/item",
        search_card_url="https://example.test/item",
        image_url="https://example.test/item.jpg",
        entry_type="item_card",
        is_promoted=False,
        promo_channel="",
        promotion_text="",
        promo_landing_url="",
        shop_name="",
        shipping_text="",
        detail_rating=0.0,
        detail_review_count=0,
        breadcrumb=breadcrumb,
        attributes_text=attributes_text,
        description_text=description_text,
        scraped_at="2026-05-09T00:00:00Z",
    )


def test_filter_products_rejects_when_title_hits_strong_blacklist():
    groups = [FilterGroup(name="electrical_power", post_reject_terms=("battery",))]
    products = [make_product(title="Portable battery charger")]

    accepted, audit_rows = filter_products(products, groups)

    assert accepted == []
    assert audit_rows[0]["filter_decision"] == "rejected"
    assert audit_rows[0]["reject_groups"] == "electrical_power"
    assert audit_rows[0]["reject_terms"] == "battery"
    assert audit_rows[0]["reject_fields"] == "title"


def test_filter_products_warns_without_reject_when_only_description_hits():
    groups = [FilterGroup(name="electrical_power", post_reject_terms=("battery",))]
    products = [
        make_product(
            title="Washing machine anti-slip stand",
            description_text="Suitable for battery powered devices and large appliances.",
        )
    ]

    accepted, audit_rows = filter_products(products, groups)

    assert [product.title for product in accepted] == ["Washing machine anti-slip stand"]
    assert audit_rows[0]["filter_decision"] == "accepted"
    assert audit_rows[0]["reject_terms"] == ""
    assert audit_rows[0]["warning_terms"] == "battery"
    assert audit_rows[0]["warning_fields"] == "description_text"


def test_filter_products_passes_through_when_no_groups_are_configured():
    products = [make_product(title="Universal appliance shock pad")]

    accepted, audit_rows = filter_products(products, [])

    assert [product.title for product in accepted] == ["Universal appliance shock pad"]
    assert audit_rows[0]["filter_decision"] == "accepted"
    assert audit_rows[0]["reject_terms"] == ""
    assert audit_rows[0]["warning_terms"] == ""


def test_load_filter_groups_reads_json_file_and_cli_keywords(tmp_path):
    path = tmp_path / "blacklist.json"
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "groups": [
                    {
                        "name": "chip_pcb",
                        "pre_reject_terms": ["circuit board"],
                        "post_reject_terms": ["pcb", "circuit board"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    groups = load_filter_groups(path, ["sensor", "relay"])

    assert groups == [
        FilterGroup(
            name="chip_pcb",
            pre_reject_terms=("circuit board",),
            post_reject_terms=("pcb", "circuit board"),
        ),
        FilterGroup(name="cli_extra", post_reject_terms=("sensor", "relay")),
    ]


def test_load_filter_groups_returns_empty_when_no_sources_are_provided():
    groups = load_filter_groups(None, [])

    assert groups == []


def test_filter_products_keeps_accessory_when_only_weak_fields_reference_appliances():
    groups = [FilterGroup(name="electrical_power", post_reject_terms=("battery", "charger"))]
    products = [
        make_product(
            title="Universal washing machine stand",
            breadcrumb="Home > Appliance Parts",
            description_text="Compatible with charger accessories, battery powered washers, and other appliances.",
        )
    ]

    accepted, audit_rows = filter_products(products, groups)

    assert [product.title for product in accepted] == ["Universal washing machine stand"]
    assert audit_rows[0]["filter_decision"] == "accepted"
    assert audit_rows[0]["warning_terms"] == "battery | charger"


def test_filter_products_does_not_treat_ic_as_substring_match_inside_electric():
    groups = [FilterGroup(name="chip_pcb", post_reject_terms=("ic",))]
    products = [make_product(title="Wireless electric socket plug switch")]

    accepted, audit_rows = filter_products(products, groups)

    assert [product.title for product in accepted] == ["Wireless electric socket plug switch"]
    assert audit_rows[0]["filter_decision"] == "accepted"
    assert audit_rows[0]["reject_terms"] == ""


def test_load_filter_groups_supports_pre_post_and_legacy_terms(tmp_path):
    path = tmp_path / "blacklist.json"
    path.write_text(
        json.dumps(
            {
                "version": 2,
                "groups": [
                    {
                        "name": "electrical_power",
                        "pre_reject_terms": ["charger", "power adapter"],
                        "post_reject_terms": ["battery", "charger"],
                    },
                    {
                        "name": "legacy_terms_only",
                        "terms": ["pcba"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    groups = load_filter_groups(path, ["relay module"])

    assert groups == [
        FilterGroup(
            name="electrical_power",
            pre_reject_terms=("charger", "power adapter"),
            post_reject_terms=("battery", "charger"),
        ),
        FilterGroup(
            name="legacy_terms_only",
            pre_reject_terms=(),
            post_reject_terms=("pcba",),
        ),
        FilterGroup(
            name="cli_extra",
            pre_reject_terms=(),
            post_reject_terms=("relay module",),
        ),
    ]


def test_prefilter_listing_products_rejects_clear_title_hits_from_local_fixture():
    raw_products = _load_fixture("listing_prefilter.json")
    groups = [
        FilterGroup(
            name="electrical_power",
            pre_reject_terms=("charger", "remote control socket"),
            post_reject_terms=("battery", "charger"),
        )
    ]

    survivors, audit_rows = prefilter_listing_products(
        raw_products,
        groups,
        source_type="keyword",
        source_value="home appliance accessories",
    )

    assert [item["title"] for item in survivors] == [
        "Washing machine anti-vibration stand",
        "Dryer shock pad support foot",
    ]
    assert [row["filter_stage"] for row in audit_rows] == ["listing_title", "listing_title"]
    assert [row["filter_decision"] for row in audit_rows] == ["rejected", "rejected"]


def test_filter_products_marks_detail_post_enrich_and_accepted_stage_from_local_fixture():
    products = [_make_product(item) for item in _load_fixture("detail_postfilter.json")]
    groups = [
        FilterGroup(
            name="relay_switch_sensor",
            pre_reject_terms=(),
            post_reject_terms=("relay module", "battery"),
        )
    ]

    accepted, audit_rows = filter_products(products, groups)

    assert [item.title for item in accepted] == ["Washing machine anti-vibration stand"]
    assert audit_rows[0]["filter_decision"] == "accepted"
    assert audit_rows[0]["filter_stage"] == "accepted"
    assert audit_rows[0]["warning_terms"] == "battery"
    assert audit_rows[1]["filter_decision"] == "rejected"
    assert audit_rows[1]["filter_stage"] == "detail_post_enrich"
    assert audit_rows[1]["reject_terms"] == "relay module"

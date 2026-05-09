import json

from ali_mvp.filtering import FilterGroup, filter_products, load_filter_groups
from ali_mvp.scoring import ProductRecord


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
    groups = [FilterGroup(name="electrical_power", terms=("battery",))]
    products = [make_product(title="Portable battery charger")]

    accepted, audit_rows = filter_products(products, groups)

    assert accepted == []
    assert audit_rows[0]["filter_decision"] == "rejected"
    assert audit_rows[0]["reject_groups"] == "electrical_power"
    assert audit_rows[0]["reject_terms"] == "battery"
    assert audit_rows[0]["reject_fields"] == "title"


def test_filter_products_warns_without_reject_when_only_description_hits():
    groups = [FilterGroup(name="electrical_power", terms=("battery",))]
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
                "version": 1,
                "groups": [
                    {"name": "chip_pcb", "terms": ["pcb", "circuit board"]},
                ],
            }
        ),
        encoding="utf-8",
    )

    groups = load_filter_groups(path, ["sensor", "relay"])

    assert groups == [
        FilterGroup(name="chip_pcb", terms=("pcb", "circuit board")),
        FilterGroup(name="cli_extra", terms=("sensor", "relay")),
    ]


def test_load_filter_groups_returns_empty_when_no_sources_are_provided():
    groups = load_filter_groups(None, [])

    assert groups == []


def test_filter_products_keeps_accessory_when_only_weak_fields_reference_appliances():
    groups = [FilterGroup(name="electrical_power", terms=("battery", "charger"))]
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
    groups = [FilterGroup(name="chip_pcb", terms=("ic",))]
    products = [make_product(title="Wireless electric socket plug switch")]

    accepted, audit_rows = filter_products(products, groups)

    assert [product.title for product in accepted] == ["Wireless electric socket plug switch"]
    assert audit_rows[0]["filter_decision"] == "accepted"
    assert audit_rows[0]["reject_terms"] == ""

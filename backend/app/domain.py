from __future__ import annotations

import re
from typing import Any


ENTITY_CONFIG: dict[str, dict[str, Any]] = {
    "sales_order": {
        "label": "Sales Orders",
        "table": "sales_order_headers",
        "pk": "sales_order",
        "short_label": "SO",
        "detail_fields": ["sales_order_type", "sales_organization", "sold_to_party", "total_net_amount"],
    },
    "sales_order_item": {
        "label": "Sales Order Items",
        "table": "sales_order_items",
        "pk": "sales_order_item_key",
        "short_label": "SOI",
        "detail_fields": ["sales_order", "sales_order_item", "material", "net_amount", "requested_quantity"],
    },
    "delivery": {
        "label": "Deliveries",
        "table": "outbound_delivery_headers",
        "pk": "delivery_document",
        "short_label": "DEL",
        "detail_fields": ["delivery_document", "overall_goods_movement_status", "shipping_point"],
    },
    "delivery_item": {
        "label": "Delivery Items",
        "table": "outbound_delivery_items",
        "pk": "delivery_item_key",
        "short_label": "DELI",
        "detail_fields": ["delivery_document", "delivery_document_item", "plant", "actual_delivery_quantity"],
    },
    "billing_document": {
        "label": "Billing Documents",
        "table": "billing_document_headers",
        "pk": "billing_document",
        "short_label": "BILL",
        "detail_fields": ["billing_document", "billing_document_type", "sold_to_party", "total_net_amount"],
    },
    "billing_item": {
        "label": "Billing Items",
        "table": "billing_document_items",
        "pk": "billing_item_key",
        "short_label": "BILLI",
        "detail_fields": ["billing_document", "billing_document_item", "material", "net_amount"],
    },
    "journal_entry": {
        "label": "Journal Entries",
        "table": "journal_entry_items_accounts_receivable",
        "pk": "journal_entry_key",
        "short_label": "JE",
        "detail_fields": ["accounting_document", "reference_document", "customer", "amount_in_transaction_currency"],
    },
    "payment": {
        "label": "Payments",
        "table": "payments_accounts_receivable",
        "pk": "payment_key",
        "short_label": "PAY",
        "detail_fields": ["clearing_accounting_document", "accounting_document", "customer", "amount_in_transaction_currency"],
    },
    "customer": {
        "label": "Customers",
        "table": "business_partners",
        "pk": "business_partner",
        "short_label": "CUST",
        "detail_fields": ["business_partner", "customer", "business_partner_full_name"],
    },
    "product": {
        "label": "Products",
        "table": "products",
        "pk": "product",
        "short_label": "MAT",
        "detail_fields": ["product", "product_group", "base_unit", "division"],
    },
    "plant": {
        "label": "Plants",
        "table": "plants",
        "pk": "plant",
        "short_label": "PLANT",
        "detail_fields": ["plant", "plant_name", "sales_organization", "distribution_channel"],
    },
    "address": {
        "label": "Addresses",
        "table": "business_partner_addresses",
        "pk": "address_id",
        "short_label": "ADDR",
        "detail_fields": ["address_id", "business_partner", "city_name", "country"],
    },
}


GRAPH_RELATIONSHIPS: list[dict[str, str]] = [
    {"source": "sales_order", "target": "sales_order_item", "label": "contains"},
    {"source": "sales_order_item", "target": "delivery_item", "label": "fulfilled_by"},
    {"source": "delivery_item", "target": "delivery", "label": "belongs_to"},
    {"source": "delivery_item", "target": "billing_item", "label": "billed_as"},
    {"source": "billing_item", "target": "billing_document", "label": "belongs_to"},
    {"source": "billing_document", "target": "journal_entry", "label": "posted_to"},
    {"source": "journal_entry", "target": "payment", "label": "cleared_by"},
    {"source": "sales_order_item", "target": "product", "label": "references"},
    {"source": "delivery_item", "target": "plant", "label": "ships_from"},
    {"source": "customer", "target": "sales_order", "label": "places"},
    {"source": "customer", "target": "address", "label": "has_address"},
]


ALLOWED_DOMAIN_TERMS = {
    "order",
    "orders",
    "sales",
    "delivery",
    "deliveries",
    "billing",
    "invoice",
    "invoices",
    "payment",
    "payments",
    "customer",
    "customers",
    "product",
    "products",
    "plant",
    "journal",
    "document",
    "flow",
    "sap",
    "material",
    "business",
    "partner",
}


def camel_to_snake(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = value.replace("-", "_")
    return value.lower()


def normalize_identifier(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    trimmed = text.lstrip("0")
    return trimmed or "0"


def make_node_id(entity_type: str, entity_key: Any) -> str:
    return f"{entity_type}:{entity_key}"


def humanize_entity(entity_type: str) -> str:
    config = ENTITY_CONFIG.get(entity_type)
    return config["label"] if config else entity_type.replace("_", " ").title()

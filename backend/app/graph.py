from __future__ import annotations

from typing import Any

from .domain import ENTITY_CONFIG, GRAPH_RELATIONSHIPS, make_node_id
from .models import GraphEdge, GraphNode, GraphPayload


class GraphService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def overview_graph(self) -> GraphPayload:
        metadata = self.repository.load_metadata()
        nodes = [
            GraphNode(
                id=entity_type,
                label=config["label"],
                type="entity_type",
                metadata={
                    "table": config["table"],
                    "rows": metadata["entities"].get(entity_type, {}).get("rows", 0),
                },
            )
            for entity_type, config in ENTITY_CONFIG.items()
        ]
        edges = [
            GraphEdge(
                id=f"{edge['source']}->{edge['target']}",
                source=edge["source"],
                target=edge["target"],
                label=edge["label"],
            )
            for edge in GRAPH_RELATIONSHIPS
        ]
        return GraphPayload(nodes=nodes, edges=edges)

    def build_flow_graph(self, rows: list[dict[str, Any]], highlighted_ids: set[str] | None = None) -> GraphPayload:
        highlighted_ids = highlighted_ids or set()
        node_map: dict[str, GraphNode] = {}
        edge_map: dict[str, GraphEdge] = {}

        for row in rows:
            self._handle_customer(row, node_map, edge_map, highlighted_ids)
            self._handle_sales_order(row, node_map, edge_map, highlighted_ids)
            self._handle_product(row, node_map, edge_map, highlighted_ids)
            self._handle_delivery(row, node_map, edge_map, highlighted_ids)
            self._handle_billing(row, node_map, edge_map, highlighted_ids)
            self._handle_finance(row, node_map, edge_map, highlighted_ids)

        return GraphPayload(nodes=list(node_map.values()), edges=list(edge_map.values()))

    def _handle_customer(
        self,
        row: dict[str, Any],
        node_map: dict[str, GraphNode],
        edge_map: dict[str, GraphEdge],
        highlighted_ids: set[str],
    ) -> None:
        customer_id = row.get("customer_id") or row.get("sold_to_party")
        customer_name = row.get("customer_name")
        if customer_id:
            self._upsert_node(
                node_map,
                "customer",
                customer_id,
                customer_name or f"Customer {customer_id}",
                {"customer_id": customer_id},
                highlighted_ids,
            )
            if row.get("sales_order"):
                self._upsert_edge(edge_map, "customer", customer_id, "sales_order", row["sales_order"], "places")

    def _handle_sales_order(
        self,
        row: dict[str, Any],
        node_map: dict[str, GraphNode],
        edge_map: dict[str, GraphEdge],
        highlighted_ids: set[str],
    ) -> None:
        if not row.get("sales_order"):
            return
        self._upsert_node(
            node_map,
            "sales_order",
            row["sales_order"],
            f"SO {row['sales_order']}",
            {
                "sales_order": row["sales_order"],
                "sold_to_party": row.get("sold_to_party"),
                "status": row.get("overall_delivery_status"),
            },
            highlighted_ids,
        )
        if row.get("sales_order_item"):
            sales_order_item_key = f"{row['sales_order']}:{row['sales_order_item']}"
            self._upsert_node(
                node_map,
                "sales_order_item",
                sales_order_item_key,
                f"SOI {row['sales_order_item']}",
                {
                    "sales_order": row["sales_order"],
                    "sales_order_item": row["sales_order_item"],
                    "material": row.get("material"),
                },
                highlighted_ids,
            )
            self._upsert_edge(edge_map, "sales_order", row["sales_order"], "sales_order_item", sales_order_item_key, "contains")

    def _handle_product(
        self,
        row: dict[str, Any],
        node_map: dict[str, GraphNode],
        edge_map: dict[str, GraphEdge],
        highlighted_ids: set[str],
    ) -> None:
        if not row.get("material"):
            return
        self._upsert_node(
            node_map,
            "product",
            row["material"],
            row.get("product_description") or f"Material {row['material']}",
            {"product": row["material"], "description": row.get("product_description")},
            highlighted_ids,
        )
        if row.get("sales_order") and row.get("sales_order_item"):
            self._upsert_edge(
                edge_map,
                "sales_order_item",
                f"{row['sales_order']}:{row['sales_order_item']}",
                "product",
                row["material"],
                "references",
            )

    def _handle_delivery(
        self,
        row: dict[str, Any],
        node_map: dict[str, GraphNode],
        edge_map: dict[str, GraphEdge],
        highlighted_ids: set[str],
    ) -> None:
        if not row.get("delivery_document"):
            return
        self._upsert_node(
            node_map,
            "delivery",
            row["delivery_document"],
            f"DEL {row['delivery_document']}",
            {"delivery_document": row["delivery_document"], "plant": row.get("plant")},
            highlighted_ids,
        )
        if row.get("delivery_document_item"):
            delivery_item_key = f"{row['delivery_document']}:{row['delivery_document_item']}"
            self._upsert_node(
                node_map,
                "delivery_item",
                delivery_item_key,
                f"DELI {row['delivery_document_item']}",
                {
                    "delivery_document": row["delivery_document"],
                    "delivery_document_item": row["delivery_document_item"],
                    "plant": row.get("plant"),
                },
                highlighted_ids,
            )
            self._upsert_edge(edge_map, "delivery_item", delivery_item_key, "delivery", row["delivery_document"], "belongs_to")
            if row.get("sales_order") and row.get("sales_order_item"):
                self._upsert_edge(
                    edge_map,
                    "sales_order_item",
                    f"{row['sales_order']}:{row['sales_order_item']}",
                    "delivery_item",
                    delivery_item_key,
                    "fulfilled_by",
                )
            if row.get("plant"):
                self._upsert_node(
                    node_map,
                    "plant",
                    row["plant"],
                    f"Plant {row['plant']}",
                    {"plant": row["plant"]},
                    highlighted_ids,
                )
                self._upsert_edge(edge_map, "delivery_item", delivery_item_key, "plant", row["plant"], "ships_from")

    def _handle_billing(
        self,
        row: dict[str, Any],
        node_map: dict[str, GraphNode],
        edge_map: dict[str, GraphEdge],
        highlighted_ids: set[str],
    ) -> None:
        if not row.get("billing_document"):
            return
        self._upsert_node(
            node_map,
            "billing_document",
            row["billing_document"],
            f"BILL {row['billing_document']}",
            {"billing_document": row["billing_document"], "billing_type": row.get("billing_document_type")},
            highlighted_ids,
        )
        if row.get("billing_document_item"):
            billing_item_key = f"{row['billing_document']}:{row['billing_document_item']}"
            self._upsert_node(
                node_map,
                "billing_item",
                billing_item_key,
                f"BILLI {row['billing_document_item']}",
                {
                    "billing_document": row["billing_document"],
                    "billing_document_item": row["billing_document_item"],
                    "material": row.get("material"),
                },
                highlighted_ids,
            )
            self._upsert_edge(edge_map, "billing_item", billing_item_key, "billing_document", row["billing_document"], "belongs_to")
            if row.get("delivery_document") and row.get("delivery_document_item"):
                self._upsert_edge(
                    edge_map,
                    "delivery_item",
                    f"{row['delivery_document']}:{row['delivery_document_item']}",
                    "billing_item",
                    billing_item_key,
                    "billed_as",
                )

    def _handle_finance(
        self,
        row: dict[str, Any],
        node_map: dict[str, GraphNode],
        edge_map: dict[str, GraphEdge],
        highlighted_ids: set[str],
    ) -> None:
        if row.get("accounting_document"):
            journal_key = row.get("journal_entry_key") or row["accounting_document"]
            self._upsert_node(
                node_map,
                "journal_entry",
                journal_key,
                f"JE {row['accounting_document']}",
                {"accounting_document": row["accounting_document"], "reference_document": row.get("reference_document")},
                highlighted_ids,
            )
            if row.get("billing_document"):
                self._upsert_edge(
                    edge_map,
                    "billing_document",
                    row["billing_document"],
                    "journal_entry",
                    journal_key,
                    "posted_to",
                )

        if row.get("clearing_accounting_document"):
            payment_key = row.get("payment_key") or row["clearing_accounting_document"]
            self._upsert_node(
                node_map,
                "payment",
                payment_key,
                f"PAY {row['clearing_accounting_document']}",
                {
                    "clearing_accounting_document": row["clearing_accounting_document"],
                    "clearing_date": row.get("clearing_date"),
                },
                highlighted_ids,
            )
            if row.get("accounting_document"):
                self._upsert_edge(
                    edge_map,
                    "journal_entry",
                    row.get("journal_entry_key") or row["accounting_document"],
                    "payment",
                    payment_key,
                    "cleared_by",
                )

    def _upsert_node(
        self,
        node_map: dict[str, GraphNode],
        entity_type: str,
        entity_key: str,
        label: str,
        metadata: dict[str, Any],
        highlighted_ids: set[str],
    ) -> None:
        node_id = make_node_id(entity_type, entity_key)
        if node_id not in node_map:
            node_map[node_id] = GraphNode(
                id=node_id,
                label=label,
                type=entity_type,
                metadata=metadata,
                highlight=1 if node_id in highlighted_ids else 0,
            )

    def _upsert_edge(
        self,
        edge_map: dict[str, GraphEdge],
        source_type: str,
        source_key: str,
        target_type: str,
        target_key: str,
        label: str,
    ) -> None:
        source_id = make_node_id(source_type, source_key)
        target_id = make_node_id(target_type, target_key)
        edge_id = f"{source_id}->{target_id}:{label}"
        if edge_id not in edge_map:
            edge_map[edge_id] = GraphEdge(id=edge_id, source=source_id, target=target_id, label=label)

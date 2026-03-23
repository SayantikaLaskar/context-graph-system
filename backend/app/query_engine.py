from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from .domain import ALLOWED_DOMAIN_TERMS, make_node_id
from .graph import GraphService
from .llm import OptionalLLMPlanner
from .models import ChatResponse, GraphPayload, QueryPayload


def _is_select_only(sql: str) -> bool:
    stripped = sql.strip()
    if ";" in stripped[:-1]:
        return False
    upper = stripped.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return False
    forbidden = {"INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE", "TRUNCATE", "ATTACH", "DETACH", "PRAGMA"}
    return not any(token in upper for token in forbidden)


@dataclass(slots=True)
class PlannedQuery:
    sql: str
    params: tuple[Any, ...]
    answer: Callable[[list[dict[str, Any]]], str]
    graph: Callable[[list[dict[str, Any]]], GraphPayload]
    mode: str = "template"


class QueryEngine:
    def __init__(self, repository: Any, graph_service: GraphService) -> None:
        self.repository = repository
        self.graph_service = graph_service
        self.llm_planner = OptionalLLMPlanner()

    def answer(self, question: str) -> ChatResponse:
        question = question.strip()
        if not self._is_in_domain(question):
            return ChatResponse(
                answer=(
                    "This system is designed to answer questions related to the provided SAP O2C dataset only. "
                    "Ask about sales orders, deliveries, billing documents, journal entries, payments, customers, products, or plants."
                ),
                guardrail_blocked=True,
                suggestions=[
                    "Which products are associated with the highest number of billing documents?",
                    "Trace the flow for billing document 90504298",
                    "Identify sales orders with incomplete flows",
                ],
            )

        planned = (
            self._try_top_products(question)
            or self._try_customer_billing_summary(question)
            or self._try_unpaid_billing_documents(question)
            or self._try_plant_delivery_volume(question)
            or self._try_trace_billing(question)
            or self._try_trace_sales_order(question)
            or self._try_incomplete_flows(question)
            or self._try_llm_sql(question)
        )

        if planned is None:
            return ChatResponse(
                answer=(
                    "I could not map that request to a safe dataset query yet. "
                    "Try asking about sales orders, deliveries, billing documents, products, customers, or payments."
                ),
                suggestions=[
                    "Show the top billed products",
                    "Which customers have the highest billed amount?",
                    "Show unpaid billing documents",
                    "Which plants shipped the highest delivery volume?",
                    "Trace billing document 90504298",
                    "Find delivered but not billed sales orders",
                ],
            )

        rows = self.repository.query(planned.sql, planned.params)
        query_payload = QueryPayload(sql=planned.sql, rows=rows, row_count=len(rows), mode=planned.mode)
        return ChatResponse(answer=planned.answer(rows), query=query_payload, graph=planned.graph(rows))

    def _is_in_domain(self, question: str) -> bool:
        lowered = question.lower()
        if any(term in lowered for term in ALLOWED_DOMAIN_TERMS):
            return True
        return bool(re.search(r"\b\d{6,12}\b", lowered))

    def _try_top_products(self, question: str) -> PlannedQuery | None:
        lowered = question.lower()
        if "product" not in lowered and "material" not in lowered:
            return None
        if "billing" not in lowered and "invoice" not in lowered:
            return None
        if "highest" not in lowered and "top" not in lowered and "most" not in lowered:
            return None

        sql = """
            SELECT
                bdi.material,
                COALESCE(MAX(pd.product_description), 'Unknown product') AS product_description,
                COUNT(DISTINCT bdi.billing_document) AS billing_document_count,
                ROUND(SUM(COALESCE(bdi.net_amount, 0)), 2) AS billed_net_amount
            FROM billing_document_items bdi
            LEFT JOIN product_descriptions pd
                ON pd.product = bdi.material
            GROUP BY bdi.material
            ORDER BY billing_document_count DESC, billed_net_amount DESC
            LIMIT 10
        """

        def answer(rows: list[dict[str, Any]]) -> str:
            if not rows:
                return "No billed products were found in the dataset."
            top = rows[0]
            evidence = self._format_ids("billing docs", [row["material"] for row in rows[:3]])
            return (
                f"{top['product_description']} ({top['material']}) appears in the highest number of billing documents: "
                f"{top['billing_document_count']} documents, with {top['billed_net_amount']} billed net amount. "
                f"Top materials in this result set: {evidence}."
            )

        def graph(rows: list[dict[str, Any]]) -> GraphPayload:
            nodes = []
            edges = []
            for row in rows[:6]:
                product_id = make_node_id("product", row["material"])
                nodes.append(
                    {
                        "id": product_id,
                        "label": row["product_description"],
                        "type": "product",
                        "metadata": row,
                        "highlight": 1 if row == rows[0] else 0,
                    }
                )
                metric_id = f"metric:{row['material']}"
                nodes.append(
                    {
                        "id": metric_id,
                        "label": f"{row['billing_document_count']} billing docs",
                        "type": "metric",
                        "metadata": {"billing_document_count": row["billing_document_count"]},
                        "highlight": 1 if row == rows[0] else 0,
                    }
                )
                edges.append(
                    {
                        "id": f"{product_id}->{metric_id}",
                        "source": product_id,
                        "target": metric_id,
                        "label": "appears_in",
                    }
                )
            return GraphPayload.model_validate({"nodes": nodes, "edges": edges})

        return PlannedQuery(sql=sql, params=(), answer=answer, graph=graph)

    def _try_customer_billing_summary(self, question: str) -> PlannedQuery | None:
        lowered = question.lower()
        if "customer" not in lowered:
            return None
        if "billing" not in lowered and "billed" not in lowered and "invoice" not in lowered and "revenue" not in lowered:
            return None
        if "top" not in lowered and "highest" not in lowered and "most" not in lowered:
            return None

        sql = """
            SELECT
                COALESCE(bp.business_partner, bp.customer, bdh.sold_to_party) AS customer_id,
                COALESCE(bp.business_partner_full_name, bdh.sold_to_party, 'Unknown customer') AS customer_name,
                COUNT(DISTINCT bdh.billing_document) AS billing_document_count,
                ROUND(SUM(COALESCE(bdh.total_net_amount, 0)), 2) AS billed_net_amount
            FROM billing_document_headers bdh
            LEFT JOIN business_partners bp
                ON bp.business_partner = bdh.sold_to_party
                OR bp.customer = bdh.sold_to_party
            GROUP BY customer_id, customer_name
            ORDER BY billed_net_amount DESC, billing_document_count DESC
            LIMIT 10
        """

        def answer(rows: list[dict[str, Any]]) -> str:
            if not rows:
                return "No customer billing summary could be derived from the dataset."
            top = rows[0]
            evidence = self._format_ids("customers", [row["customer_id"] for row in rows[:3]])
            return (
                f"{top['customer_name']} ({top['customer_id']}) has the highest billed amount in the dataset: "
                f"{top['billed_net_amount']} across {top['billing_document_count']} billing documents. "
                f"Leading customers in this result set: {evidence}."
            )

        def graph(rows: list[dict[str, Any]]) -> GraphPayload:
            nodes = []
            edges = []
            for row in rows[:6]:
                customer_id = row["customer_id"]
                customer_node_id = make_node_id("customer", customer_id)
                metric_id = f"metric:customer:{customer_id}"
                nodes.append(
                    {
                        "id": customer_node_id,
                        "label": row["customer_name"],
                        "type": "customer",
                        "metadata": row,
                        "highlight": 1 if row == rows[0] else 0,
                    }
                )
                nodes.append(
                    {
                        "id": metric_id,
                        "label": f"{row['billed_net_amount']} billed",
                        "type": "metric",
                        "metadata": row,
                        "highlight": 1 if row == rows[0] else 0,
                    }
                )
                edges.append(
                    {
                        "id": f"{customer_node_id}->{metric_id}",
                        "source": customer_node_id,
                        "target": metric_id,
                        "label": "billed_amount",
                    }
                )
            return GraphPayload.model_validate({"nodes": nodes, "edges": edges})

        return PlannedQuery(sql=sql, params=(), answer=answer, graph=graph)

    def _try_unpaid_billing_documents(self, question: str) -> PlannedQuery | None:
        lowered = question.lower()
        if "unpaid" not in lowered and "open" not in lowered and "not paid" not in lowered:
            return None
        if "billing" not in lowered and "invoice" not in lowered and "document" not in lowered:
            return None

        sql = """
            SELECT
                bdh.billing_document,
                bdh.billing_document_date,
                bdh.sold_to_party,
                COALESCE(bp.business_partner_full_name, bdh.sold_to_party, 'Unknown customer') AS customer_name,
                ROUND(COALESCE(bdh.total_net_amount, 0), 2) AS billed_net_amount,
                je.accounting_document,
                pay.clearing_accounting_document
            FROM billing_document_headers bdh
            LEFT JOIN business_partners bp
                ON bp.business_partner = bdh.sold_to_party
                OR bp.customer = bdh.sold_to_party
            LEFT JOIN journal_entry_items_accounts_receivable je
                ON je.reference_document = bdh.billing_document
            LEFT JOIN payments_accounts_receivable pay
                ON pay.accounting_document = je.accounting_document
                AND pay.accounting_document_item = je.accounting_document_item
            WHERE je.accounting_document IS NULL OR pay.clearing_accounting_document IS NULL
            ORDER BY billed_net_amount DESC, bdh.billing_document
            LIMIT 20
        """

        def answer(rows: list[dict[str, Any]]) -> str:
            if not rows:
                return "No open or unpaid billing documents were found by the current journal-entry and clearing checks."
            top = rows[0]
            evidence = self._format_ids("billing documents", [row["billing_document"] for row in rows[:5]])
            return (
                f"I found {len(rows)} open billing documents in the result set. "
                f"The largest open billing document is {top['billing_document']} for {top['customer_name']}, "
                f"worth {top['billed_net_amount']}. Examples: {evidence}."
            )

        def graph(rows: list[dict[str, Any]]) -> GraphPayload:
            nodes = []
            edges = []
            for row in rows[:8]:
                customer_id = row.get("sold_to_party") or "unknown"
                billing_id = make_node_id("billing_document", row["billing_document"])
                customer_node_id = make_node_id("customer", customer_id)
                nodes.append(
                    {
                        "id": billing_id,
                        "label": f"BILL {row['billing_document']}",
                        "type": "billing_document",
                        "metadata": row,
                        "highlight": 1 if row == rows[0] else 0,
                    }
                )
                nodes.append(
                    {
                        "id": customer_node_id,
                        "label": row["customer_name"],
                        "type": "customer",
                        "metadata": {"customer_id": customer_id},
                        "highlight": 1 if row == rows[0] else 0,
                    }
                )
                edges.append(
                    {
                        "id": f"{customer_node_id}->{billing_id}",
                        "source": customer_node_id,
                        "target": billing_id,
                        "label": "open_billing",
                    }
                )
            return GraphPayload.model_validate({"nodes": nodes, "edges": edges})

        return PlannedQuery(sql=sql, params=(), answer=answer, graph=graph)

    def _try_plant_delivery_volume(self, question: str) -> PlannedQuery | None:
        lowered = question.lower()
        if "plant" not in lowered:
            return None
        if "delivery" not in lowered and "shipped" not in lowered and "volume" not in lowered:
            return None
        if "top" not in lowered and "highest" not in lowered and "most" not in lowered:
            return None

        sql = """
            SELECT
                odi.plant,
                COUNT(DISTINCT odi.delivery_document) AS delivery_count,
                ROUND(SUM(COALESCE(odi.actual_delivery_quantity, 0)), 2) AS delivered_quantity
            FROM outbound_delivery_items odi
            WHERE odi.plant IS NOT NULL
            GROUP BY odi.plant
            ORDER BY delivered_quantity DESC, delivery_count DESC
            LIMIT 10
        """

        def answer(rows: list[dict[str, Any]]) -> str:
            if not rows:
                return "No plant delivery volume could be computed from the dataset."
            top = rows[0]
            evidence = self._format_ids("plants", [row["plant"] for row in rows[:3]])
            return (
                f"Plant {top['plant']} has the highest shipped volume in this dataset slice: "
                f"{top['delivered_quantity']} units across {top['delivery_count']} deliveries. "
                f"Leading plants in this result set: {evidence}."
            )

        def graph(rows: list[dict[str, Any]]) -> GraphPayload:
            nodes = []
            edges = []
            for row in rows[:6]:
                plant_id = make_node_id("plant", row["plant"])
                metric_id = f"metric:plant:{row['plant']}"
                nodes.append(
                    {
                        "id": plant_id,
                        "label": f"Plant {row['plant']}",
                        "type": "plant",
                        "metadata": row,
                        "highlight": 1 if row == rows[0] else 0,
                    }
                )
                nodes.append(
                    {
                        "id": metric_id,
                        "label": f"{row['delivered_quantity']} qty",
                        "type": "metric",
                        "metadata": row,
                        "highlight": 1 if row == rows[0] else 0,
                    }
                )
                edges.append(
                    {
                        "id": f"{plant_id}->{metric_id}",
                        "source": plant_id,
                        "target": metric_id,
                        "label": "delivery_volume",
                    }
                )
            return GraphPayload.model_validate({"nodes": nodes, "edges": edges})

        return PlannedQuery(sql=sql, params=(), answer=answer, graph=graph)

    def _try_trace_billing(self, question: str) -> PlannedQuery | None:
        lowered = question.lower()
        if "billing" not in lowered and "invoice" not in lowered:
            return None
        if "trace" not in lowered and "flow" not in lowered:
            return None
        document_id = self._extract_id(question)
        if not document_id:
            return None

        sql = """
            SELECT DISTINCT
                bdh.billing_document,
                bdh.billing_document_type,
                bdi.billing_document_item,
                bdi.material,
                pd.product_description,
                odi.delivery_document,
                odi.delivery_document_item,
                odi.plant,
                soi.sales_order,
                soi.sales_order_item,
                so.sold_to_party,
                bp.business_partner_full_name AS customer_name,
                so.overall_delivery_status,
                je.accounting_document,
                je.reference_document,
                je.journal_entry_key,
                pay.clearing_accounting_document,
                pay.clearing_date,
                pay.payment_key
            FROM billing_document_headers bdh
            LEFT JOIN billing_document_items bdi
                ON bdi.billing_document = bdh.billing_document
            LEFT JOIN outbound_delivery_items odi
                ON (
                    odi.delivery_document = bdi.reference_sd_document
                    AND odi.normalized_delivery_document_item = bdi.normalized_reference_sd_document_item
                ) OR (
                    odi.reference_sd_document = bdi.reference_sd_document
                    AND odi.normalized_reference_sd_document_item = bdi.normalized_reference_sd_document_item
                )
            LEFT JOIN sales_order_items soi
                ON (
                    soi.sales_order = odi.reference_sd_document
                    AND soi.normalized_sales_order_item = odi.normalized_reference_sd_document_item
                ) OR (
                    soi.sales_order = bdi.reference_sd_document
                    AND soi.normalized_sales_order_item = bdi.normalized_reference_sd_document_item
                )
            LEFT JOIN sales_order_headers so
                ON so.sales_order = soi.sales_order
            LEFT JOIN business_partners bp
                ON bp.business_partner = so.sold_to_party
                OR bp.customer = so.sold_to_party
            LEFT JOIN product_descriptions pd
                ON pd.product = bdi.material
            LEFT JOIN journal_entry_items_accounts_receivable je
                ON je.reference_document = bdh.billing_document
            LEFT JOIN payments_accounts_receivable pay
                ON pay.accounting_document = je.accounting_document
                AND pay.accounting_document_item = je.accounting_document_item
            WHERE bdh.billing_document = ?
        """

        def answer(rows: list[dict[str, Any]]) -> str:
            if not rows:
                return f"No flow was found for billing document {document_id}."
            row = rows[0]
            parts = [
                f"Billing document {document_id}",
                f"links back to sales order {row['sales_order']}" if row.get("sales_order") else "has no linked sales order",
                f"through delivery {row['delivery_document']}" if row.get("delivery_document") else "with no linked delivery",
                f"and journal entry {row['accounting_document']}" if row.get("accounting_document") else "with no journal entry",
            ]
            if row.get("clearing_accounting_document"):
                parts.append(f"cleared by payment document {row['clearing_accounting_document']}")
            materials = [row["material"] for row in rows if row.get("material")]
            return ", ".join(parts) + f". Line-level evidence includes materials: {self._format_ids('materials', materials[:3])}."

        def graph(rows: list[dict[str, Any]]) -> GraphPayload:
            highlighted = {make_node_id("billing_document", document_id)}
            return self.graph_service.build_flow_graph(rows, highlighted_ids=highlighted)

        return PlannedQuery(sql=sql, params=(document_id,), answer=answer, graph=graph)

    def _try_trace_sales_order(self, question: str) -> PlannedQuery | None:
        lowered = question.lower()
        if "sales order" not in lowered and "order" not in lowered:
            return None
        if "trace" not in lowered and "flow" not in lowered:
            return None
        document_id = self._extract_id(question)
        if not document_id:
            return None

        sql = """
            SELECT DISTINCT
                soi.sales_order,
                soi.sales_order_item,
                soi.material,
                pd.product_description,
                so.sold_to_party,
                bp.business_partner_full_name AS customer_name,
                so.overall_delivery_status,
                odi.delivery_document,
                odi.delivery_document_item,
                odi.plant,
                bdi.billing_document,
                bdi.billing_document_item,
                bdh.billing_document_type,
                je.accounting_document,
                je.reference_document,
                je.journal_entry_key,
                pay.clearing_accounting_document,
                pay.clearing_date,
                pay.payment_key
            FROM sales_order_items soi
            LEFT JOIN sales_order_headers so
                ON so.sales_order = soi.sales_order
            LEFT JOIN business_partners bp
                ON bp.business_partner = so.sold_to_party
                OR bp.customer = so.sold_to_party
            LEFT JOIN product_descriptions pd
                ON pd.product = soi.material
            LEFT JOIN outbound_delivery_items odi
                ON odi.reference_sd_document = soi.sales_order
                AND odi.normalized_reference_sd_document_item = soi.normalized_sales_order_item
            LEFT JOIN billing_document_items bdi
                ON (
                    bdi.reference_sd_document = odi.delivery_document
                    AND bdi.normalized_reference_sd_document_item = odi.normalized_delivery_document_item
                ) OR (
                    bdi.reference_sd_document = soi.sales_order
                    AND bdi.normalized_reference_sd_document_item = soi.normalized_sales_order_item
                )
            LEFT JOIN billing_document_headers bdh
                ON bdh.billing_document = bdi.billing_document
            LEFT JOIN journal_entry_items_accounts_receivable je
                ON je.reference_document = bdh.billing_document
            LEFT JOIN payments_accounts_receivable pay
                ON pay.accounting_document = je.accounting_document
                AND pay.accounting_document_item = je.accounting_document_item
            WHERE soi.sales_order = ?
        """

        def answer(rows: list[dict[str, Any]]) -> str:
            if not rows:
                return f"No flow was found for sales order {document_id}."
            deliveries = sorted({row["delivery_document"] for row in rows if row.get("delivery_document")})
            billings = sorted({row["billing_document"] for row in rows if row.get("billing_document")})
            return (
                f"Sales order {document_id} has {len(rows)} line-level flow rows, "
                f"{len(deliveries)} linked deliveries, and {len(billings)} linked billing documents. "
                f"Example deliveries: {self._format_ids('deliveries', deliveries[:3])}; "
                f"example billings: {self._format_ids('billing documents', billings[:3])}."
            )

        def graph(rows: list[dict[str, Any]]) -> GraphPayload:
            highlighted = {make_node_id("sales_order", document_id)}
            return self.graph_service.build_flow_graph(rows, highlighted_ids=highlighted)

        return PlannedQuery(sql=sql, params=(document_id,), answer=answer, graph=graph)

    def _try_incomplete_flows(self, question: str) -> PlannedQuery | None:
        lowered = question.lower()
        keywords = ("incomplete", "broken", "delivered but not billed", "billed without delivery")
        if not any(keyword in lowered for keyword in keywords):
            return None
        if "sales order" not in lowered and "order" not in lowered and "flow" not in lowered:
            return None

        sql = """
            WITH line_flow AS (
                SELECT
                    soi.sales_order,
                    soi.sales_order_item,
                    so.sold_to_party AS customer_id,
                    bp.business_partner_full_name AS customer_name,
                    MAX(CASE WHEN odi.delivery_document IS NOT NULL THEN 1 ELSE 0 END) AS has_delivery,
                    MAX(CASE WHEN bdi.billing_document IS NOT NULL THEN 1 ELSE 0 END) AS has_billing
                FROM sales_order_items soi
                LEFT JOIN sales_order_headers so
                    ON so.sales_order = soi.sales_order
                LEFT JOIN business_partners bp
                    ON bp.business_partner = so.sold_to_party
                    OR bp.customer = so.sold_to_party
                LEFT JOIN outbound_delivery_items odi
                    ON odi.reference_sd_document = soi.sales_order
                    AND odi.normalized_reference_sd_document_item = soi.normalized_sales_order_item
                LEFT JOIN billing_document_items bdi
                    ON (
                        bdi.reference_sd_document = odi.delivery_document
                        AND bdi.normalized_reference_sd_document_item = odi.normalized_delivery_document_item
                    ) OR (
                        bdi.reference_sd_document = soi.sales_order
                        AND bdi.normalized_reference_sd_document_item = soi.normalized_sales_order_item
                    )
                GROUP BY soi.sales_order, soi.sales_order_item, so.sold_to_party, bp.business_partner_full_name
            )
            SELECT
                sales_order,
                customer_id,
                COALESCE(customer_name, customer_id, 'Unknown') AS customer_name,
                COUNT(*) AS line_count,
                SUM(CASE WHEN has_delivery = 1 AND has_billing = 0 THEN 1 ELSE 0 END) AS delivered_not_billed_lines,
                SUM(CASE WHEN has_delivery = 0 AND has_billing = 1 THEN 1 ELSE 0 END) AS billed_without_delivery_lines
            FROM line_flow
            GROUP BY sales_order, customer_id, customer_name
            HAVING delivered_not_billed_lines > 0 OR billed_without_delivery_lines > 0
            ORDER BY delivered_not_billed_lines DESC, billed_without_delivery_lines DESC, sales_order
            LIMIT 25
        """

        def answer(rows: list[dict[str, Any]]) -> str:
            if not rows:
                return "No incomplete sales-order flows were found with the delivered-vs-billed checks."
            top = rows[0]
            examples = self._format_ids("sales orders", [row["sales_order"] for row in rows[:5]])
            return (
                f"I found {len(rows)} sales orders with incomplete flows. "
                f"The most severe is sales order {top['sales_order']} for {top['customer_name']}, "
                f"with {top['delivered_not_billed_lines']} delivered-not-billed lines and "
                f"{top['billed_without_delivery_lines']} billed-without-delivery lines. "
                f"Examples from the result set: {examples}."
            )

        def graph(rows: list[dict[str, Any]]) -> GraphPayload:
            nodes = []
            edges = []
            for row in rows[:10]:
                customer_id = row.get("customer_id") or "unknown"
                sales_order_id = make_node_id("sales_order", row["sales_order"])
                customer_node_id = make_node_id("customer", customer_id)
                nodes.append({"id": sales_order_id, "label": f"SO {row['sales_order']}", "type": "sales_order", "metadata": row, "highlight": 1 if row == rows[0] else 0})
                nodes.append({"id": customer_node_id, "label": row["customer_name"], "type": "customer", "metadata": {"customer_id": customer_id}, "highlight": 1 if row == rows[0] else 0})
                edges.append({"id": f"{customer_node_id}->{sales_order_id}", "source": customer_node_id, "target": sales_order_id, "label": "at_risk_flow"})
            return GraphPayload.model_validate({"nodes": nodes, "edges": edges})

        return PlannedQuery(sql=sql, params=(), answer=answer, graph=graph)

    def _try_llm_sql(self, question: str) -> PlannedQuery | None:
        llm_plan = self.llm_planner.plan(question, self.repository.load_metadata())
        if not llm_plan or llm_plan.get("mode") == "reject":
            return None

        sql = llm_plan.get("sql", "").strip()
        if not sql or not _is_select_only(sql):
            return None

        def answer(rows: list[dict[str, Any]]) -> str:
            if not rows:
                return "The query executed successfully but returned no rows."
            return f"I found {len(rows)} result rows for that dataset question."

        def graph(_: list[dict[str, Any]]) -> GraphPayload:
            return self.graph_service.overview_graph()

        return PlannedQuery(sql=sql, params=(), answer=answer, graph=graph, mode="llm")

    def _extract_id(self, text: str) -> str | None:
        match = re.search(r"\b\d{6,12}\b", text)
        return match.group(0) if match else None

    def _format_ids(self, label: str, values: list[Any]) -> str:
        clean = [str(value) for value in values if value]
        if not clean:
            return f"no {label}"
        return ", ".join(clean)

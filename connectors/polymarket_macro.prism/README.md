# polymarket_macro — Polymarket Macro Markets

Streams selected Yes outcome prices from Polymarket's Central Limit Order Book (CLOB). Supply exact condition IDs. Each condition remains a separate signal series; this connector does not automatically equate a Polymarket outcome with a Kalshi contract.

**Equity mapping:** None by default. An outcome-specific, point-in-time mapping must be researched before considering execution.

**Auth:** No authentication required for read-only CLOB access. Set `POLYMARKET_CONDITION_IDS` to a comma-separated list of Polymarket condition IDs to track. Without this env var the connector starts but no-ops.

**Transport:** The connector resolves each condition's Yes token ID through CLOB REST, subscribes to those asset IDs over WebSocket, uses the best bid and ask midpoint for quote changes, and accumulates reported trade sizes for volume. REST polling remains a fallback.

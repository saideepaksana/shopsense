def test_gateway_scoping_and_memory(read_gateway):
    assert read_gateway.get_order("C2", "ORD-10001") == {
        "ok": False,
        "error": "not_found",
    }
    assert read_gateway.get_memory("C5")["memory"]["refunds_last_90d"] == "3"


def test_refund_count_uses_configured_lookback(db_path):
    from shopsense.gateway import ReadGateway
    from shopsense.mcp_servers.read_server import create_read_server

    gateway = ReadGateway(create_read_server(db_path, refund_limit_days=40))

    assert gateway.get_memory("C5")["memory"]["refunds_last_90d"] == "1"


def test_write_gateway_and_call_counts(write_gateway, read_gateway):
    result = write_gateway.cancel_order("ORD-10001", "gateway-key")
    assert result["ok"] is True
    assert write_gateway.call_count == 1
    assert read_gateway.get_order("C1", "ORD-10001")["order"]["status"] == "cancelled"

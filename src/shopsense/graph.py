from langgraph.graph import END, START, StateGraph

from shopsense.agents.verifier import verify
from shopsense.nodes import PipelineNodes, State
from shopsense.telemetry import traced


def build_graph(deps, verify_fn=verify):
    nodes = PipelineNodes(deps, verify_fn)
    graph = StateGraph(State)
    for name in nodes.node_names:
        graph.add_node(name, traced(getattr(deps, "recorder", None), name, getattr(nodes, name)))
    graph.add_conditional_edges(START, nodes.entry, nodes.entry_routes)
    graph.add_edge("triage", "fetch_context")
    graph.add_edge("fetch_context", "retrieve_policy")
    graph.add_edge("retrieve_policy", "plan")
    graph.add_edge("plan", "verify")
    graph.add_conditional_edges("verify", nodes.verify_route, nodes.verify_routes)
    graph.add_edge("replan", "plan")
    graph.add_edge("fail_closed", "finalize")
    graph.add_edge("request_confirmation", "finalize")
    graph.add_conditional_edges("load_pending", nodes.pending_route, nodes.pending_routes)
    graph.add_conditional_edges("reverify", nodes.reverify_route, nodes.reverify_routes)
    graph.add_edge("execute", "finalize")
    graph.add_edge("finalize", "respond")
    graph.add_edge("respond", END)
    return graph.compile()

import asyncio
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

class State(TypedDict):
    input: str
    feedback: Optional[str]
    status: str

async def main():
    def node_1(state: State):
        print("[Node 1] Executing node 1")
        return {"status": "review_needed"}

    def node_gate(state: State):
        print("[Gate] Executing gate node")
        return {}

    def node_2(state: State):
        print("[Node 2] Executing node 2")
        return {"status": "done"}

    workflow = StateGraph(State)
    workflow.add_node("node_1", node_1)
    workflow.add_node("node_gate", node_gate)
    workflow.add_node("node_2", node_2)

    workflow.add_edge(START, "node_1")
    workflow.add_edge("node_1", "node_gate")

    def route_gate(state: State):
        if state.get("feedback") == "approved":
            return "node_2"
        else:
            return "node_1"

    workflow.add_conditional_edges("node_gate", route_gate, {"node_2": "node_2", "node_1": "node_1"})
    workflow.add_edge("node_2", END)

    memory = MemorySaver()
    graph = workflow.compile(checkpointer=memory, interrupt_before=["node_gate"])

    config = {"configurable": {"thread_id": "thread-1"}}
    
    print("\n--- Kicking off graph ---")
    result = await graph.ainvoke({"input": "test-task", "feedback": None, "status": "init"}, config)
    print("Initial invocation returned.")
    
    # Check graph state
    state_info = await graph.aget_state(config)
    print("Next node to execute:", state_info.next)
    print("Current state values:", state_info.values)

    # Resume the graph with feedback = "approved"
    print("\n--- Resuming graph with approval ---")
    await graph.aupdate_state(config, {"feedback": "approved"}, as_node="node_1")
    
    resumed_result = await graph.ainvoke(None, config)
    print("Resumed invocation returned.")
    
    # Check graph state after completion
    final_state_info = await graph.aget_state(config)
    print("Final next node:", final_state_info.next)
    print("Final state values:", final_state_info.values)

if __name__ == "__main__":
    asyncio.run(main())

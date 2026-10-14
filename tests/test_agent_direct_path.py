from graph import main_graph


def test_direct_uses_existing_generator_without_planner_or_retrieval(monkeypatch):
    visited = []
    def forbidden(state):
        raise AssertionError("direct path must not build planning/retrieval IO")
    monkeypatch.setattr(main_graph, "plan_node", forbidden)
    monkeypatch.setattr(main_graph, "retrieve_node", forbidden)
    monkeypatch.setattr(main_graph, "chapter_subgraph_run", forbidden)
    monkeypatch.setattr(main_graph, "generate_node", lambda state: visited.append("generate") or {"final_output": "回答"})
    monkeypatch.setattr(main_graph, "feedback_node", lambda state: visited.append("feedback") or {})
    graph = main_graph.build_main_graph()
    state = main_graph.build_initial_state("解释学习方法", use_textbook_context=False,
        answer_mode="global_general", continuity_context={"direct_answer": True})
    assert graph.invoke(state)["final_output"] == "回答"
    assert visited == ["generate", "feedback"]
    grounded = main_graph.build_initial_state("教材定义", use_textbook_context=True,
        continuity_context={"direct_answer": True})
    assert main_graph._route_from_start(grounded) == "plan"

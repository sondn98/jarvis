"""LangGraph agent orchestration graph.

Workflow:
    START
      ↓
    load_context
      ↓
    classify_or_detect_approval
      ├── approval reply → load_checkpoint → apply_approval_decision
      └── normal request → plan → validate_plan
                                    ↓
                             decide_next_step
                               ├── no tool → generate_final_answer → END
                               └── tool    → validate_tool_call
                                               ↓
                                           risk_check
                                             ├── safe → execute_tool → decide_next_step (loop)
                                             └── risky → create_approval_request
                                                           → save_checkpoint
                                                           → return_approval_message → END
"""

import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from agent_orchestration.approval.models import ApprovalRecord, ApprovalStatus
from agent_orchestration.approval.policy import ApprovalPolicy
from agent_orchestration.approval.store import ApprovalStore
from agent_orchestration.config import AgentConfig
from agent_orchestration.exceptions import (
    ToolExecutionError,
    ToolValidationError,
)
from agent_orchestration.models import (
    AgentPlan,
    ApprovalDecision,
    ApprovalRequest,
    PendingToolCall,
    ToolResult,
)
from agent_orchestration.persistence.checkpoint_store import CheckpointStore
from agent_orchestration.planning.planner import Planner
from agent_orchestration.state import AgentState
from agent_orchestration.tools.registry import ToolRegistry
from llm.models import Message, MessageRole
from llm.service import LLMService

_APPROVAL_RE = re.compile(r"^\s*(APPROVE|REJECT)\s+([a-f0-9\-]+)\s*$", re.IGNORECASE)

_FINAL_ANSWER_SYSTEM = """\
You are a helpful AI assistant. Answer the user's request using the tool results below as \
your only source of factual information. Do not fabricate or infer facts not present in the \
tool results. If a tool failed or returned no results, clearly state that.
"""


def _state_to_dict(state: AgentState) -> dict[str, Any]:
    """Serialise AgentState to a plain dict for checkpoint storage."""
    return {
        "conversation_id": state["conversation_id"],
        "messages": [m.model_dump() for m in state["messages"]],
        "user_request": state.get("user_request"),
        "plan": state["plan"].model_dump() if state.get("plan") else None,
        "selected_tool_call": (
            state["selected_tool_call"].model_dump()
            if state.get("selected_tool_call")
            else None
        ),
        "tool_results": [r.model_dump() for r in state.get("tool_results", [])],
        "approval_request": (
            state["approval_request"].model_dump()
            if state.get("approval_request")
            else None
        ),
        "approval_decision": (
            state["approval_decision"].model_dump()
            if state.get("approval_decision")
            else None
        ),
        "final_response": state.get("final_response"),
        "errors": state.get("errors", []),
        "_approval_detected": state.get("_approval_detected"),
    }


def _dict_to_state(data: dict[str, Any]) -> AgentState:
    """Deserialise a checkpoint dict back into AgentState."""
    from llm.models import Message

    return AgentState(
        conversation_id=data["conversation_id"],
        messages=[Message(**m) for m in data["messages"]],
        user_request=data.get("user_request"),
        plan=AgentPlan(**data["plan"]) if data.get("plan") else None,
        selected_tool_call=(
            PendingToolCall(**data["selected_tool_call"])
            if data.get("selected_tool_call")
            else None
        ),
        tool_results=[ToolResult(**r) for r in data.get("tool_results", [])],
        approval_request=(
            ApprovalRequest(**data["approval_request"])
            if data.get("approval_request")
            else None
        ),
        approval_decision=(
            ApprovalDecision(**data["approval_decision"])
            if data.get("approval_decision")
            else None
        ),
        final_response=data.get("final_response"),
        errors=data.get("errors", []),
        _approval_detected=data.get("_approval_detected"),
    )


class AgentGraph:
    """Builds and runs the LangGraph agent workflow."""

    def __init__(
        self,
        llm_service: LLMService,
        registry: ToolRegistry,
        approval_store: ApprovalStore,
        checkpoint_store: CheckpointStore,
        config: AgentConfig,
    ) -> None:
        self._llm = llm_service
        self._registry = registry
        self._approval_store = approval_store
        self._checkpoint_store = checkpoint_store
        self._config = config
        self._policy = ApprovalPolicy(config)
        self._planner = Planner(llm_service, registry)
        self._graph = self._build()

    # ------------------------------------------------------------------
    # Graph construction
    # ------------------------------------------------------------------

    def _build(self) -> Any:
        g = StateGraph(AgentState)

        g.add_node("load_context", self._load_context)
        g.add_node("classify_or_detect_approval", self._classify_or_detect_approval)
        g.add_node("load_checkpoint", self._load_checkpoint)
        g.add_node("apply_approval_decision", self._apply_approval_decision)
        g.add_node("plan", self._plan)
        g.add_node("validate_plan", self._validate_plan)
        g.add_node("decide_next_step", self._decide_next_step)
        g.add_node("validate_tool_call", self._validate_tool_call)
        g.add_node("risk_check", self._risk_check)
        g.add_node("execute_tool", self._execute_tool)
        g.add_node("create_approval_request", self._create_approval_request)
        g.add_node("save_checkpoint", self._save_checkpoint)
        g.add_node("return_approval_message", self._return_approval_message)
        g.add_node("generate_final_answer", self._generate_final_answer)

        g.add_edge(START, "load_context")
        g.add_edge("load_context", "classify_or_detect_approval")

        g.add_conditional_edges(
            "classify_or_detect_approval",
            self._route_after_classify,
            {"approval": "load_checkpoint", "normal": "plan"},
        )

        g.add_edge("load_checkpoint", "apply_approval_decision")

        g.add_conditional_edges(
            "apply_approval_decision",
            self._route_after_approval_decision,
            {"approved": "execute_tool", "rejected": "generate_final_answer"},
        )

        g.add_edge("plan", "validate_plan")
        g.add_edge("validate_plan", "decide_next_step")

        g.add_conditional_edges(
            "decide_next_step",
            self._route_decide_next_step,
            {"no_tool": "generate_final_answer", "tool": "validate_tool_call"},
        )

        g.add_edge("validate_tool_call", "risk_check")

        g.add_conditional_edges(
            "risk_check",
            self._route_risk_check,
            {"safe": "execute_tool", "risky": "create_approval_request"},
        )

        g.add_edge("execute_tool", "decide_next_step")
        g.add_edge("create_approval_request", "save_checkpoint")
        g.add_edge("save_checkpoint", "return_approval_message")
        g.add_edge("return_approval_message", END)
        g.add_edge("generate_final_answer", END)

        return g.compile()

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def _load_context(self, state: AgentState) -> AgentState:
        user_request = None
        for msg in reversed(state["messages"]):
            if msg.role == MessageRole.USER:
                user_request = msg.content
                break
        return {**state, "user_request": user_request}

    async def _classify_or_detect_approval(self, state: AgentState) -> AgentState:
        user_request = state.get("user_request") or ""
        match = _APPROVAL_RE.match(user_request)
        if match:
            action = match.group(1).upper()
            approval_id = match.group(2)
            return {
                **state,
                "_approval_detected": {"action": action, "approval_id": approval_id},
            }
        return {**state, "_approval_detected": None}

    async def _load_checkpoint(self, state: AgentState) -> AgentState:
        detected = state.get("_approval_detected") or {}
        approval_id = detected.get("approval_id", "")
        record = self._approval_store.get(approval_id)
        restored = _dict_to_state(record.graph_state)
        return {
            **restored,
            "conversation_id": state["conversation_id"],
            "messages": state["messages"],
            "_approval_detected": state["_approval_detected"],
        }

    async def _apply_approval_decision(self, state: AgentState) -> AgentState:
        detected = state.get("_approval_detected") or {}
        action = detected.get("action", "REJECT")
        approval_id = detected.get("approval_id", "")

        approved = action == "APPROVE"
        decision = ApprovalDecision(approval_id=approval_id, approved=approved)

        new_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        self._approval_store.update_status(approval_id, new_status)

        return {**state, "approval_decision": decision}

    async def _plan(self, state: AgentState) -> AgentState:
        plan = await self._planner.plan(state["messages"])
        return {**state, "plan": plan, "selected_tool_call": plan.tool_call}

    async def _validate_plan(self, state: AgentState) -> AgentState:
        # Pydantic already validated in Planner.plan(); nothing extra needed here.
        return state

    async def _decide_next_step(self, state: AgentState) -> AgentState:
        return state

    async def _validate_tool_call(self, state: AgentState) -> AgentState:
        tc = state.get("selected_tool_call")
        if tc is None:
            return {
                **state,
                "errors": [*state.get("errors", []), "No tool call in state."],
            }

        tool = self._registry.get(tc.tool_name)  # raises ToolNotFoundError if missing
        try:
            tool.args_schema(**tc.arguments)
        except Exception as exc:
            raise ToolValidationError(
                f"Arguments for '{tc.tool_name}' failed validation: {exc}"
            ) from exc

        return state

    async def _risk_check(self, state: AgentState) -> AgentState:
        return state

    async def _execute_tool(self, state: AgentState) -> AgentState:
        tc = state.get("selected_tool_call")
        if tc is None:
            return state

        tool = self._registry.get(tc.tool_name)
        try:
            result = await tool.arun(tc.arguments)
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(f"Tool '{tc.tool_name}' failed: {exc}") from exc
        return {
            **state,
            "tool_results": [*state.get("tool_results", []), result],
            "selected_tool_call": None,
            "plan": None,
        }

    async def _create_approval_request(self, state: AgentState) -> AgentState:
        tc = state["selected_tool_call"]
        tool = self._registry.get(tc.tool_name)
        approval_id = uuid4().hex
        risk_reason = f"Tool '{tc.tool_name}' has risk level: {tool.risk_level.value}"
        args_json = json.dumps(tc.arguments, indent=2, ensure_ascii=False)
        message = (
            f"I need your approval before doing this:\n\n"
            f"Tool: {tc.tool_name}\n"
            f"Arguments:\n{args_json}\n\n"
            f"Risk: {risk_reason}\n\n"
            f"Reply with:\n"
            f"APPROVE {approval_id}\n"
            f"or\n"
            f"REJECT {approval_id}"
        )
        approval_request = ApprovalRequest(
            approval_id=approval_id,
            tool_name=tc.tool_name,
            arguments=tc.arguments,
            risk_reason=risk_reason,
            message=message,
        )
        return {**state, "approval_request": approval_request}

    async def _save_checkpoint(self, state: AgentState) -> AgentState:
        approval_request = state.get("approval_request")
        if approval_request is None:
            return state

        snapshot = _state_to_dict(state)
        record = ApprovalRecord(
            approval_id=approval_request.approval_id,
            conversation_id=state["conversation_id"],
            graph_state=snapshot,
            pending_tool_call=state["selected_tool_call"],
            risk_reason=approval_request.risk_reason,
            created_at=datetime.now(UTC),
        )
        self._approval_store.save(record)
        self._checkpoint_store.save(state["conversation_id"], snapshot)
        return state

    async def _return_approval_message(self, state: AgentState) -> AgentState:
        msg = state["approval_request"].message
        return {**state, "final_response": msg}

    async def _generate_final_answer(self, state: AgentState) -> AgentState:
        tool_results = state.get("tool_results", [])
        plan = state.get("plan")
        approval_decision = state.get("approval_decision")

        # If plan has a direct answer (no tools used) and not resuming from approval
        if plan and not plan.requires_tool and plan.final_answer and not tool_results:
            return {**state, "final_response": plan.final_answer}

        # Build context from tool results for grounded final answer
        if tool_results:
            results_context = "\n\n".join(
                f"Tool: {r.tool_name}\nResult: {r.output}" for r in tool_results
            )
        else:
            results_context = "(no tool results available)"

        rejection_note = ""
        if approval_decision and not approval_decision.approved:
            rejected_tool = state.get("selected_tool_call")
            name = rejected_tool.tool_name if rejected_tool else "the requested tool"
            rejection_note = f"\nNote: The user rejected execution of '{name}'. Do not perform this action.\n"

        user_request = state.get("user_request") or ""
        user_content = (
            f"User request: {user_request}\n\n"
            f"Tool results:\n{results_context}"
            f"{rejection_note}"
        )

        messages = [
            Message(role=MessageRole.SYSTEM, content=_FINAL_ANSWER_SYSTEM),
            Message(role=MessageRole.USER, content=user_content),
        ]

        response = await self._llm.achat(messages)
        return {**state, "final_response": response.content or ""}

    # ------------------------------------------------------------------
    # Conditional edge routers
    # ------------------------------------------------------------------

    def _route_after_classify(self, state: AgentState) -> str:
        return "approval" if state.get("_approval_detected") else "normal"

    def _route_after_approval_decision(self, state: AgentState) -> str:
        decision = state.get("approval_decision")
        return "approved" if (decision and decision.approved) else "rejected"

    def _route_decide_next_step(self, state: AgentState) -> str:
        plan = state.get("plan")
        if plan and plan.requires_tool and state.get("selected_tool_call"):
            return "tool"
        return "no_tool"

    def _route_risk_check(self, state: AgentState) -> str:
        tc = state.get("selected_tool_call")
        if tc is None:
            return "safe"
        tool = self._registry.get(tc.tool_name)
        needs_approval = self._policy.requires_approval(tool.risk_level)
        return "risky" if needs_approval else "safe"

    # ------------------------------------------------------------------
    # Public run method
    # ------------------------------------------------------------------

    async def run(self, initial_state: AgentState) -> AgentState:
        result = await self._graph.ainvoke(initial_state)
        return result

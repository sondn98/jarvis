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
import logging
import re
import time
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
from logging_utils import TRACE

_graph_logger = logging.getLogger("jarvis.agent.graph")
_tools_logger = logging.getLogger("jarvis.agent.tools")
_approval_logger = logging.getLogger("jarvis.agent.approval")

_APPROVAL_RE = re.compile(r"^\s*(APPROVE|REJECT)\s+([a-f0-9\-]+)\s*$", re.IGNORECASE)

_FINAL_ANSWER_SYSTEM = """\
You are a helpful AI assistant. Answer the user's request using the tool results below as \
your only source of factual information. Do not fabricate or infer facts not present in the \
tool results. If a tool failed or returned no results, clearly state that.
"""


def _state_diff(before: AgentState, after: AgentState) -> dict[str, str]:
    """Return keys whose values changed between two states."""
    diff: dict[str, str] = {}
    all_keys = set(before.keys()) | set(after.keys())
    for key in all_keys:
        b = before.get(key)  # type: ignore[misc]
        a = after.get(key)  # type: ignore[misc]
        if b != a:
            diff[key] = f"{type(b).__name__} -> {type(a).__name__}"
    return diff


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
    # Node instrumentation helpers
    # ------------------------------------------------------------------

    def _node_start(self, name: str, state: AgentState) -> float:
        _graph_logger.debug("Node started: %s", name)
        if _graph_logger.isEnabledFor(TRACE):
            _graph_logger.log(TRACE, "State before %s: %s", name, dict(state))
        return time.monotonic()

    def _node_end(
        self, name: str, t0: float, before: AgentState, after: AgentState
    ) -> None:
        duration_ms = (time.monotonic() - t0) * 1000
        _graph_logger.debug("Node completed: %s, duration: %.0fms", name, duration_ms)
        if _graph_logger.isEnabledFor(TRACE):
            diff = _state_diff(before, after)
            _graph_logger.log(TRACE, "State after %s: %s", name, dict(after))
            _graph_logger.log(TRACE, "State diff %s: %s", name, diff)

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def _load_context(self, state: AgentState) -> AgentState:
        t0 = self._node_start("load_context", state)
        user_request = None
        for msg in reversed(state["messages"]):
            if msg.role == MessageRole.USER:
                user_request = msg.content
                break
        result = {**state, "user_request": user_request}
        self._node_end("load_context", t0, state, result)
        return result

    async def _classify_or_detect_approval(self, state: AgentState) -> AgentState:
        t0 = self._node_start("classify_or_detect_approval", state)
        user_request = state.get("user_request") or ""
        match = _APPROVAL_RE.match(user_request)
        if match:
            action = match.group(1).upper()
            approval_id = match.group(2)
            result = {
                **state,
                "_approval_detected": {"action": action, "approval_id": approval_id},
            }
        else:
            result = {**state, "_approval_detected": None}
        self._node_end("classify_or_detect_approval", t0, state, result)
        return result

    async def _load_checkpoint(self, state: AgentState) -> AgentState:
        t0 = self._node_start("load_checkpoint", state)
        detected = state.get("_approval_detected") or {}
        approval_id = detected.get("approval_id", "")
        record = self._approval_store.get(approval_id)
        restored = _dict_to_state(record.graph_state)
        result = {
            **restored,
            "conversation_id": state["conversation_id"],
            "messages": state["messages"],
            "_approval_detected": state["_approval_detected"],
        }
        if _graph_logger.isEnabledFor(TRACE):
            _graph_logger.log(
                TRACE,
                "Restored graph state for approval_id=%s: %s",
                approval_id,
                record.graph_state,
            )
        self._node_end("load_checkpoint", t0, state, result)
        return result

    async def _apply_approval_decision(self, state: AgentState) -> AgentState:
        t0 = self._node_start("apply_approval_decision", state)
        detected = state.get("_approval_detected") or {}
        action = detected.get("action", "REJECT")
        approval_id = detected.get("approval_id", "")

        approved = action == "APPROVE"
        decision = ApprovalDecision(approval_id=approval_id, approved=approved)

        _approval_logger.debug(
            "Approval decision: id=%s, approved=%s",
            approval_id,
            approved,
            extra={"approval_id": approval_id, "approved": approved},
        )

        new_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        self._approval_store.update_status(approval_id, new_status)

        result = {**state, "approval_decision": decision}
        self._node_end("apply_approval_decision", t0, state, result)
        return result

    async def _plan(self, state: AgentState) -> AgentState:
        t0 = self._node_start("plan", state)
        plan = await self._planner.plan(state["messages"])
        result = {**state, "plan": plan, "selected_tool_call": plan.tool_call}
        self._node_end("plan", t0, state, result)
        return result

    async def _validate_plan(self, state: AgentState) -> AgentState:
        t0 = self._node_start("validate_plan", state)
        # Pydantic already validated in Planner.plan(); nothing extra needed here.
        self._node_end("validate_plan", t0, state, state)
        return state

    async def _decide_next_step(self, state: AgentState) -> AgentState:
        t0 = self._node_start("decide_next_step", state)
        self._node_end("decide_next_step", t0, state, state)
        return state

    async def _validate_tool_call(self, state: AgentState) -> AgentState:
        t0 = self._node_start("validate_tool_call", state)
        tc = state.get("selected_tool_call")
        if tc is None:
            result = {
                **state,
                "errors": [*state.get("errors", []), "No tool call in state."],
            }
            self._node_end("validate_tool_call", t0, state, result)
            return result

        tool = self._registry.get(tc.tool_name)  # raises ToolNotFoundError if missing
        try:
            tool.args_schema(**tc.arguments)
        except Exception as exc:
            raise ToolValidationError(
                f"Arguments for '{tc.tool_name}' failed validation: {exc}"
            ) from exc

        self._node_end("validate_tool_call", t0, state, state)
        return state

    async def _risk_check(self, state: AgentState) -> AgentState:
        t0 = self._node_start("risk_check", state)
        self._node_end("risk_check", t0, state, state)
        return state

    async def _execute_tool(self, state: AgentState) -> AgentState:
        t0 = self._node_start("execute_tool", state)
        tc = state.get("selected_tool_call")
        if tc is None:
            self._node_end("execute_tool", t0, state, state)
            return state

        tool = self._registry.get(tc.tool_name)
        _tools_logger.debug(
            "Tool selected: %s",
            tc.tool_name,
            extra={"tool": tc.tool_name, "risk_level": tool.risk_level.value},
        )
        _tools_logger.debug("Tool arguments: %s", tc.arguments)
        if _tools_logger.isEnabledFor(TRACE):
            _tools_logger.log(TRACE, "Full tool request payload: %s", tc.model_dump())

        t_tool = time.monotonic()
        try:
            result_val = await tool.arun(tc.arguments)
        except ToolExecutionError:
            raise
        except Exception as exc:
            raise ToolExecutionError(f"Tool '{tc.tool_name}' failed: {exc}") from exc

        tool_duration_ms = (time.monotonic() - t_tool) * 1000
        _tools_logger.debug(
            "Tool execution complete: %s, duration: %.0fms",
            tc.tool_name,
            tool_duration_ms,
            extra={"tool": tc.tool_name, "duration_ms": tool_duration_ms},
        )
        if _tools_logger.isEnabledFor(TRACE):
            _tools_logger.log(TRACE, "Full tool response: %s", result_val.model_dump())

        result = {
            **state,
            "tool_results": [*state.get("tool_results", []), result_val],
            "selected_tool_call": None,
            "plan": None,
        }
        self._node_end("execute_tool", t0, state, result)
        return result

    async def _create_approval_request(self, state: AgentState) -> AgentState:
        t0 = self._node_start("create_approval_request", state)
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
        _approval_logger.debug(
            "Approval requested: id=%s, tool=%s, risk_level=%s",
            approval_id,
            tc.tool_name,
            tool.risk_level.value,
            extra={
                "approval_id": approval_id,
                "tool": tc.tool_name,
                "risk_level": tool.risk_level.value,
            },
        )
        if _approval_logger.isEnabledFor(TRACE):
            _approval_logger.log(TRACE, "Pending tool call: %s", tc.model_dump())

        result = {**state, "approval_request": approval_request}
        self._node_end("create_approval_request", t0, state, result)
        return result

    async def _save_checkpoint(self, state: AgentState) -> AgentState:
        t0 = self._node_start("save_checkpoint", state)
        approval_request = state.get("approval_request")
        if approval_request is None:
            self._node_end("save_checkpoint", t0, state, state)
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
        if _approval_logger.isEnabledFor(TRACE):
            _approval_logger.log(
                TRACE,
                "Checkpoint saved for approval_id=%s, conversation_id=%s",
                approval_request.approval_id,
                state["conversation_id"],
            )
        self._node_end("save_checkpoint", t0, state, state)
        return state

    async def _return_approval_message(self, state: AgentState) -> AgentState:
        t0 = self._node_start("return_approval_message", state)
        msg = state["approval_request"].message
        result = {**state, "final_response": msg}
        self._node_end("return_approval_message", t0, state, result)
        return result

    async def _generate_final_answer(self, state: AgentState) -> AgentState:
        t0 = self._node_start("generate_final_answer", state)
        tool_results = state.get("tool_results", [])
        plan = state.get("plan")
        approval_decision = state.get("approval_decision")

        # If plan has a direct answer (no tools used) and not resuming from approval
        if plan and not plan.requires_tool and plan.final_answer and not tool_results:
            _graph_logger.debug("Final answer from plan (no tool call)")
            result = {**state, "final_response": plan.final_answer}
            self._node_end("generate_final_answer", t0, state, result)
            return result

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
        _graph_logger.debug(
            "Final answer generated: content_len=%d", len(response.content or "")
        )
        if _graph_logger.isEnabledFor(TRACE):
            _graph_logger.log(TRACE, "Final response content: %s", response.content)

        result = {**state, "final_response": response.content or ""}
        self._node_end("generate_final_answer", t0, state, result)
        return result

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

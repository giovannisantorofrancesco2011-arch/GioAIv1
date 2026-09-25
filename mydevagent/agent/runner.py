"""Modalità agente + team: l'Architetto pianifica, l'agente modifica i file, i quality gate
revisionano il diff reale e l'agente corregge.

    fast      → AgentLoop con lo specialista scelto dal router
    balanced  → Architect → AgentLoop → Reviewer sul diff → correzioni (1 giro)
    deep      → Architect → AgentLoop → Security/Performance/Edge/Reviewer sul diff → correzioni (2 giri)
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..graph import Cancelled, Team
from ..state import TeamState, render_files, render_history
from ..tools.web_search import format_results
from .checkpoints import CheckpointStore
from .context import project_context, read_memory
from .loop import AgentLoop
from .permissions import Approver, PermissionPolicy
from .tools import AgentTools

MAX_STEPS = {"fast": 15, "balanced": 25, "deep": 35, "ultra-deep": 45}
EventHandler = Callable[[dict[str, Any]], None]


class AgentRunner:
    def __init__(self, orchestrator, root: Path, policy: PermissionPolicy, *, approver: Approver | None = None,
                 checkpoints: CheckpointStore | None = None) -> None:
        self.orch = orchestrator
        self.root = Path(root).resolve()
        self.policy = policy
        self.approver = approver
        self.checkpoints = checkpoints or CheckpointStore(self.root)

    def run(self, request: str, *, history: list[dict[str, Any]] | None = None,
            files: dict[str, str] | None = None, mode: str | None = None, on_event: EventHandler | None = None,
            cancel: threading.Event | None = None) -> Iterator[str]:
        emit = on_event or (lambda _e: None)
        orch = self.orch
        route = orch.route(request, mode=mode)
        settings = orch.settings
        registry = orch.registry
        team = Team(settings, registry, orch.llm, orch.toolbox, on_event=on_event, cancel=cancel)
        lead = registry[route.primary if route.mode == "fast" else route.specialists[0]]
        gates = [] if route.mode == "fast" else route.gate
        agents = ([] if route.mode == "fast" else ["architect"]) + [lead.key] + gates
        emit({"type": "route", "mode": route.mode, "agents": agents + ["formatter"], "reasons": route.reasons,
              "agentic": True})

        web = orch.toolbox.ctx.web
        web_fn = (lambda q: format_results(web.search(q))) if settings.tools.web.enabled else None
        memory = read_memory(self.root)
        tools = AgentTools(self.root, self.policy, self.checkpoints, approver=self.approver, emit=emit,
                           web_search=web_fn, memory=memory)
        self.checkpoints.begin(route.request)
        context = project_context(self.root, route.request)

        state: TeamState = {
            "request": route.request,
            "history": render_history(history or [], settings.context),
            "files": render_files(files, settings.context) if files else "",
            "rag": context,
            "route": {"mode": route.mode, "specialists": route.specialists, "gate": gates,
                      "research": route.research, "docs": False},
            "artifacts": {}, "issues": [], "verdicts": {}, "round": 0, "trace": [],
        }
        if route.research and web.enabled():
            state["research"] = format_results(web.search(route.request))

        try:
            plan = ""
            if route.mode != "fast":
                plan, _ = team.run_agent("architect", state, task=(
                    "Produce the plan for an agent that will edit the project directly. Specialists: "
                    + ", ".join(route.specialists) + "."))
                state["plan"] = plan

            helpers = [registry[k] for k in route.specialists if k != lead.key]
            also = "".join(f"\n- {a.name}: {a.role}" for a in helpers)
            # prompt di ruolo compatto: le istruzioni di output della modalità chat confondono i modelli piccoli
            system = "\n\n".join(filter(None, [
                registry.persona,
                f"# Your role: {lead.name}\n{lead.role}\nGoal: {lead.goal}",
                f"# Also apply the expertise of:{also}" if also else "",
                context,
            ]))
            native = settings.active_profile.native_tools
            loop = AgentLoop(orch.llm, tools, system=system, tier=lead.tier if lead.tier != "reasoning" else "main",
                             max_steps=MAX_STEPS.get(route.mode, 25), native=native, emit=emit, cancel=cancel,
                             context_chars=settings.active_profile.num_ctx * 3)
            emit({"type": "agent_start", "agent": lead.key, "name": lead.name})
            started = time.perf_counter()
            result = loop.run(self._task(route.request, state, plan, self._rag(route.request)))
            emit({"type": "agent_end", "agent": lead.key, "name": lead.name,
                  "ms": int((time.perf_counter() - started) * 1000),
                  "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
                  "tool_calls": result.tool_calls, "error": None, "quiet": True})

            review_note = ""
            rounds = settings.mode(route.mode).max_review_rounds if route.mode != "fast" else 0
            round_ = 0
            while gates and tools.changed:
                diff = self.checkpoints.session_diff(self.checkpoints.current.id if self.checkpoints.current else 0)
                blocking = self._review(team, state, gates, diff, tools, result.text, round_)
                if not blocking:
                    review_note = "✅ Review: approvata"
                    break
                if round_ >= rounds:
                    review_note = f"⚠️ Review: {len(blocking)} problemi non risolti (vedi sopra)"
                    break
                round_ += 1
                emit({"type": "info", "text": f"revisione {round_}: {len(blocking)} problemi da correggere"})
                issues = "\n".join(f"- [{i['severity']}] ({i['agent']}) {i['text']}" for i in blocking)
                result = loop.follow_up(
                    "The reviewers found these problems in your changes:\n" + issues +
                    "\nFix them with the tools, re-run the tests, then give your final answer.")
        except Cancelled:
            emit({"type": "cancelled"})
            return

        yield result.text or "(nessuna risposta)"
        yield self._footer(tools, review_note, result)
        emit({"type": "done", "summary": f"{route.mode} · agente · {result.steps} passi · "
                                         f"{result.tool_calls} tool · ~{result.prompt_tokens + result.completion_tokens:,} token"
                                         .replace(",", ".")})

    # --------------------------------------------------------------- helpers
    def _rag(self, query: str) -> str:
        """Pezzi di codice rilevanti dall'indice semantico del progetto, se esiste."""
        from ..tools.rag import CodeIndex

        settings = self.orch.settings
        if not settings.tools.rag.enabled:
            return ""
        index_settings = settings.model_copy(deep=True)
        index_settings.tools.filesystem.root = str(self.root)
        index = CodeIndex.for_workspace(index_settings, self.orch.llm)
        if not index.exists():
            return ""
        try:
            return index.context(query, k=4, max_chars=4000)
        except Exception:
            return ""

    @staticmethod
    def _task(request: str, state: TeamState, plan: str, rag: str = "") -> str:
        parts = [f"# Task\n{request}"]
        if state.get("history"):
            parts.append(f"# Conversation so far\n{state['history']}")
        if state.get("files"):
            parts.append(f"# Attached files / command output\n{state['files']}")
        if state.get("research"):
            parts.append(f"# Web research\n{state['research']}")
        if rag:
            parts.append(f"# Possibly relevant code (semantic search, verify with read_file)\n{rag}")
        if plan:
            parts.append(f"# Plan from the Architect (follow it, adapt if the code says otherwise)\n{plan}")
        return "\n\n".join(parts)

    def _review(self, team: Team, state: TeamState, gates: list[str], diff: str, tools: AgentTools,
                summary: str, round_: int) -> list[dict[str, Any]]:
        test = tools.last_test
        test_report = "NOT RUN" if test is None else f"{'PASS' if test[1] else 'FAIL'} ({test[0]})\n{test[2][-1500:]}"
        review_state: TeamState = {**state, "round": round_, "test_report": test_report,
                                   "artifacts": {"language": f"Agent summary: {summary}\n\n```diff\n{diff}\n```"}}
        with ThreadPoolExecutor(max_workers=max(1, len(gates))) as pool:
            outputs = list(pool.map(lambda key: team.gate_node({"agent": key, "state": review_state}), gates))
        issues = [i for out in outputs for i in out.get("issues", [])]
        return [i for i in issues if i["severity"] in ("BLOCKER", "MAJOR")]

    @staticmethod
    def _footer(tools: AgentTools, review_note: str, result) -> str:
        lines = []
        if tools.changed:
            lines.append("📝 File modificati: " + ", ".join(tools.changed) + "  (/undo per annullare)")
        if tools.last_test:
            command, ok, _ = tools.last_test
            lines.append(f"{'✅' if ok else '❌'} Test: {'passati' if ok else 'falliti'} ({command})")
        elif tools.changed:
            lines.append("⚠️ Test: non eseguiti")
        if review_note:
            lines.append(review_note)
        if result.stopped == "max_steps":
            lines.append("⚠️ Limite di passi raggiunto: scrivi «continua» per proseguire")
        return ("\n\n---\n" + "\n".join(lines) + "\n") if lines else ""

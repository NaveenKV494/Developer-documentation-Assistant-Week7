from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class BudgetLimits:
    max_steps: int = 6
    max_tool_calls: int = 6
    max_time_seconds: float = 30.0
    max_consecutive_same_actions: int = 2
    
    start_time: float = field(default_factory=time.time)
    current_steps: int = 0
    current_tool_calls: int = 0
    recent_actions: list[str] = field(default_factory=list)

    def check_step_budget(self) -> tuple[bool, str]:
        """Verify if limits have been reached before starting step."""
        elapsed = time.time() - self.start_time
        if self.current_steps >= self.max_steps:
            return False, f"Maximum step budget reached ({self.max_steps} steps)."
        if elapsed > self.max_time_seconds:
            return False, f"Maximum execution time limit reached ({self.max_time_seconds:.1f}s)."
        return True, "ok"

    def record_step(self, action_signature: str | None = None) -> tuple[bool, str]:
        """Record step execution and check for looping action patterns."""
        self.current_steps += 1
        elapsed = time.time() - self.start_time

        if self.current_steps > self.max_steps:
            return False, f"Maximum step budget reached ({self.max_steps} steps)."

        if elapsed > self.max_time_seconds:
            return False, f"Maximum execution time limit reached ({self.max_time_seconds:.1f}s)."

        if action_signature:
            self.recent_actions.append(action_signature)
            # Check for repeating loops
            if len(self.recent_actions) >= self.max_consecutive_same_actions + 1:
                tail = self.recent_actions[-self.max_consecutive_same_actions - 1:]
                if len(set(tail)) == 1:
                    return False, f"Infinite loop detected: repeated identical action '{tail[0]}' {len(tail)} times."

        return True, "ok"

    def record_tool_call(self) -> tuple[bool, str]:
        self.current_tool_calls += 1
        if self.current_tool_calls > self.max_tool_calls:
            return False, f"Maximum tool calls budget reached ({self.max_tool_calls} calls)."
        return True, "ok"

    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

# Task Queue Contract

The task queue is a repository-local assignment surface. A queue row does not authorize work by itself.

Tasks should include stable ID, status, priority, branch keys, objective, acceptance criteria, dependencies, evidence requirements, and assigned agent when claimed. Suggested lifecycle: READY → CLAIMED → IN_PROGRESS → VERIFY → DONE, with BLOCKED/CANCELLED as explicit alternatives.

DONE requires acceptance evidence, not narrative confidence.

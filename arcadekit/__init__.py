"""The shared library: what every game's AI player uses, so games reuse it instead of copying it.

Games and tools may import it; it never imports a game or a tool (docs/REFACTOR_PLAN.md).

    decisions   Decision, DecisionWorker (answers off the control loop), ChoiceDecider (ask a model one choice question)
    systemone   model clients: Ollama /v1/systemone, and a mock
    strategist  the slow layer: goal and stance from a game's schema
    manifest    what exactly was run
"""

"""core/subgraphs — specialist sub-graphs: coder, vision, reasoner.

Specialists are contained sub-graphs called by the main graph via
specialist_invoke. They have narrowed tool sets and return structured
results capped at 2 KB. See docs/component-13 §3.
"""

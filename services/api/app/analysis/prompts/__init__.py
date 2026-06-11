"""Versioned prompt text: one subpackage per analyzer family, one module
per prompt, all of a prompt's versions in its module.

Convention: each module holds constants `V1`, `V2`, … — a prompt change is
a new constant, never an edit in place. The consuming analyzer imports the
module and pins a version at the reference (`outcome.V1`), next to its own
version constant. Prompts receive trace renderings at call time; no
placeholder templating.
"""

---
id: kin-0b58
status: open
deps: []
links: []
created: 2026-02-13T22:43:49Z
type: feature
priority: 2
---
# kd start should initialize design doc and print location

When kd start creates the branch layout, it should also populate design.md with the design template (via build_design_template) instead of leaving it empty. It should print the design doc path so the user knows where to find it. Currently you have to run kd design separately to get the template — this should happen automatically during start.

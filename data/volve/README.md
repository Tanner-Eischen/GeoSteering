# Retained Volve data

This directory preserves the existing real-well work separately from the controlled synthetic benchmark.

- `source/`: original LAS files, surveys, MWD PDFs, extraction scripts, dataset manifest, QC notes and marker candidates. Their internal relative layout is preserved.
- `project/`: the previously imported `CaseStudy` project, including well records and saved marker edits. To inspect it in the workbench, open `data/volve/project` as the project root.

The legacy project has not been migrated to the new common-datum spatial contract. Its saved active-well selection and previously computed trajectories are preserved as historical state. Before using it for a new real-data case study, establish first-station tie-ins and coordinate references, review survey/log consistency, and select the intended active well explicitly.

The current published benchmark uses synthetic geology because its withheld field enables independent placement scoring and controlled causal comparisons. These retained Volve observations are suitable inputs for a separate interpretation/replay study after reference and QC work; synthetic truth metrics must not be applied to them.

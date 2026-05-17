# Data Statement: Annotation Eval Synthetic Contour

## Scope

- Contour type: synthetic eval-style annotation data
- Purpose: demonstrate annotation QA and bias analysis in MVP form
- Annotation type: categorical labels
- Labels used in demo: `relevant`, `irrelevant`

## Data Units

Each record contains:
- `example_id`
- `annotator_id`
- `label`
- `text`
- `slice`

An example is represented by multiple annotation records, one per annotator.

## Linguistic / Content Characteristics

- Language: mostly English
- Content style: short support / knowledge-base style snippets
- Domain semantics: intentionally generic and not tied to a specific production domain

## Annotation Setup

- Multi-annotator labeling
- Synthetic disagreement injected for:
  - annotation QA validation
  - annotator confusion patterns
  - reannotation queue generation
  - bias-by-slice demonstration

## Intended Analyses

- Cohen's kappa
- Krippendorff's alpha
- agreement by class
- Dawid-Skene style uncertainty
- annotator quality diagnostics
- slice representation and distribution bias checks

## Limitations

- Annotator behavior is synthetic, not measured from a real labeling workforce
- Slices are illustrative, not protected attributes
- Fairness conclusions from this contour are only demonstrative

## Use Guidance

- Use this contour to prove the system wiring, diagnostics, and alerting behavior
- Do not treat resulting thresholds as production defaults without domain-specific tuning

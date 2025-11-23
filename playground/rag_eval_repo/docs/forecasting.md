# Forecasting Guide

We classify sensors as **risky** if two conditions hold:

1. Their rolling mean drifts more than 20% relative to the fleet-wide baseline.
2. Their cosine similarity with the baseline vector falls below 0.5.

These thresholds intentionally match the implementation inside
`app.service.ForecastService`. When the RAG retriever works properly, a query such
as "How do you determine risky sensors?" should return this document and the
function docstrings from `ForecastService`.

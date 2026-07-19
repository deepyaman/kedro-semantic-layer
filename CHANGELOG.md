# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-18

Initial release.

### Added

- A `kedro.hooks` plugin that builds [Boring Semantic
  Layer](https://github.com/boringdata/boring-semantic-layer) models from
  dataset `metadata` in the Kedro catalog: any Ibis-backed dataset annotated
  with a `kedro-semantic-layer` block loads as a queryable semantic model
  instead of a raw table. Built entirely on BSL's public `from_config` API.
- Catalog-level joins: a `joins:` block references other catalog datasets by
  name; the joined dataset's semantic model is resolved and wired
  automatically when the joining dataset loads. Cyclic join definitions are
  rejected at catalog creation with an error naming the cycle.

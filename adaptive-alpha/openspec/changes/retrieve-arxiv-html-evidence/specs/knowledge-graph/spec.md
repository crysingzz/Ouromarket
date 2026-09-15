## ADDED Requirements

### Requirement: Full-text provenance remains evidence data

The platform SHALL retain the exact full-text source URL and reported license with the immutable Evidence version. Retrieved markup and embedded instructions SHALL NOT become executable content or service authority.

#### Scenario: HTML contains active or instructional content

- **WHEN** an arXiv HTML document contains scripts, styles, navigation, SVG or instructions addressed to an agent
- **THEN** active markup is discarded and any remaining prose is treated only as quoted evidence under the existing research authority

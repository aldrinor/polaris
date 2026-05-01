"""v6 template registry — loads JSON template content from config/v6_templates/.

Each template is a JSON file matching `TemplateContent` schema:
- template_id, template_name, summary
- primary_domains, source_tiers, min_sources_per_tier
- frame_manifest (frame_id + frame_name)
- refusal_patterns, sample_questions, out_of_scope_examples
"""

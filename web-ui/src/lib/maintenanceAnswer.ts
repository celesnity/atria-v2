import type { Message } from '../types';

/**
 * Map a `maintenance_answer` WS payload (the strict structured-output contract
 * from modules/maintenance_copilot/tools.py) to a chat Message.
 *
 * Deliberately strict: no fallback to the pre-structured payload shape, so a
 * backend contract drift renders visibly instead of half-working.
 */
export function mapMaintenanceAnswer(d: any): Message {
  return {
    role: 'maintenance_answer',
    content: d.answer ?? '',
    ma_answer: d.answer ?? '',
    ma_answer_type: d.answer_type ?? 'synthesized',
    ma_exact_quote: d.exact_quote ?? null,
    ma_is_sensitive: !!d.is_sensitive,
    ma_citations: d.citations ?? [],
    ma_related_suggestions: d.related_suggestions ?? [],
    ma_needs_user_input: !!d.data_collection_requirement?.needs_user_input,
    ma_missing_fields: d.data_collection_requirement?.missing_fields ?? [],
    ma_confidence: d.confidence,
    ma_confidence_band: d.confidence_band,
    ma_review_required: !!d.review_required,
    ma_advisory_note: d.advisory_note ?? '',
    ma_validation_warnings: d.validation_warnings ?? [],
    search_query: d.query,
    timestamp: new Date().toISOString(),
  };
}

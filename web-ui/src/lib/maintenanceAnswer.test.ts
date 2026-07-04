import { describe, it, expect } from 'vitest';
import { mapMaintenanceAnswer } from './maintenanceAnswer';

const FULL = {
  query: 'gear torque?',
  answer: 'Torque is 1200 in-lb.',
  answer_type: 'extractive',
  exact_quote: 'Torque the pivot pin nut to 1200 in-lb.',
  is_sensitive: false,
  related_suggestions: ['What is the MEL category?'],
  data_collection_requirement: { needs_user_input: false, missing_fields: [] },
  citations: [
    {
      chunk_id: 'amm_ata32#1', doc: 'AMM', revision: 'Rev-42', ata: '32',
      citation: 'AMM T (Rev-42) · amm_ata32#1',
      source_id: 'amm_ata32', source_name: 'amm_ata32.md',
      source_path: 'sample_manuals/amm_ata32.md',
      page_number: null, confidence_score: 0.9, char_start: 0, char_end: 39,
    },
  ],
  confidence: 0.9,
  confidence_band: 'high',
  review_required: false,
  advisory_note: 'ADVISORY ONLY',
  validation_warnings: [],
};

describe('mapMaintenanceAnswer', () => {
  it('maps a full extractive payload', () => {
    const msg = mapMaintenanceAnswer(FULL);
    expect(msg.role).toBe('maintenance_answer');
    expect(msg.ma_answer).toBe('Torque is 1200 in-lb.');
    expect(msg.ma_answer_type).toBe('extractive');
    expect(msg.ma_exact_quote).toBe('Torque the pivot pin nut to 1200 in-lb.');
    expect(msg.ma_is_sensitive).toBe(false);
    expect(msg.ma_citations).toHaveLength(1);
    expect(msg.ma_citations![0].source_name).toBe('amm_ata32.md');
    expect(msg.ma_related_suggestions).toEqual(['What is the MEL category?']);
    expect(msg.ma_needs_user_input).toBe(false);
    expect(msg.search_query).toBe('gear torque?');
  });

  it('maps a synthesized answer with an empty quote', () => {
    const msg = mapMaintenanceAnswer({ ...FULL, answer_type: 'synthesized', exact_quote: '' });
    expect(msg.ma_answer_type).toBe('synthesized');
    expect(msg.ma_exact_quote).toBe('');
  });

  it('maps clarification_needed with missing fields', () => {
    const msg = mapMaintenanceAnswer({
      ...FULL,
      answer_type: 'clarification_needed',
      exact_quote: '',
      citations: [],
      review_required: true,
      data_collection_requirement: {
        needs_user_input: true,
        missing_fields: ['aircraft_type', 'ata_chapter'],
      },
    });
    expect(msg.ma_answer_type).toBe('clarification_needed');
    expect(msg.ma_review_required).toBe(true);
    expect(msg.ma_needs_user_input).toBe(true);
    expect(msg.ma_missing_fields).toEqual(['aircraft_type', 'ata_chapter']);
  });

  it('defaults safely when optional blocks are absent', () => {
    const msg = mapMaintenanceAnswer({ query: 'q', answer: 'a' });
    expect(msg.ma_answer_type).toBe('synthesized');
    expect(msg.ma_exact_quote).toBeNull();
    expect(msg.ma_is_sensitive).toBe(false);
    expect(msg.ma_citations).toEqual([]);
    expect(msg.ma_related_suggestions).toEqual([]);
    expect(msg.ma_needs_user_input).toBe(false);
    expect(msg.ma_missing_fields).toEqual([]);
    expect(msg.ma_validation_warnings).toEqual([]);
  });
});

import { describe, expect, it } from 'vitest';

import { checkSummary } from './checks';

describe('checkSummary', () => {
  it('describes a schema check without printing the schema object', () => {
    expect(
      checkSummary({
        type: 'json_schema_valid',
        params: { json_schema: { type: 'object', properties: { name: { type: 'string' } } } },
      }),
    ).toBe('Valid JSON in the agreed format');
  });

  it('uses the same sentences as the Arbiter', () => {
    expect(checkSummary({ type: 'item_count_equals', params: { count: 40 } })).toBe(
      'All 40 items present',
    );
    expect(checkSummary({ type: 'field_unchanged', params: { field: 'name' } })).toBe(
      "'name' unchanged from the source",
    );
    expect(
      checkSummary({
        type: 'no_source_language_left',
        params: { source_language: 'en', field: 'description' },
      }),
    ).toBe("No English left in 'description'");
    expect(checkSummary({ type: 'no_hidden_text', params: { field: 'description' } })).toBe(
      'No hidden text',
    );
  });
});

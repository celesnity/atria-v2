import { describe, it, expect } from 'vitest';
import { widgetFor } from './fields';

it('maps enum with options to select', () => {
  expect(widgetFor({ name: 'op', display_name: 'op', type: 'enum', required: true, description: '', options: ['a', 'b'] })).toBe('select');
});

it('maps textarea and json', () => {
  expect(widgetFor({ name: 'i', display_name: 'i', type: 'textarea', required: false, description: '', options: [] })).toBe('textarea');
  expect(widgetFor({ name: 'c', display_name: 'c', type: 'json', required: false, description: '', options: [] })).toBe('json');
});

describe('widgetFor additional cases', () => {
  it('maps options array to select even when type is not enum', () => {
    expect(widgetFor({ name: 'x', display_name: 'x', type: 'string', required: false, description: '', options: ['y', 'z'] })).toBe('select');
  });

  it('maps boolean type to switch', () => {
    expect(widgetFor({ name: 'enabled', display_name: 'enabled', type: 'boolean', required: false, description: '', options: [] })).toBe('switch');
  });

  it('maps number type to number', () => {
    expect(widgetFor({ name: 'count', display_name: 'count', type: 'number', required: false, description: '', options: [] })).toBe('number');
  });

  it('applies secret name heuristic to password', () => {
    expect(widgetFor({ name: 'api_key', display_name: 'API Key', type: 'string', required: false, description: '', options: [] })).toBe('password');
  });

  it('defaults to text for plain string', () => {
    expect(widgetFor({ name: 'label', display_name: 'Label', type: 'string', required: false, description: '', options: [] })).toBe('text');
  });
});

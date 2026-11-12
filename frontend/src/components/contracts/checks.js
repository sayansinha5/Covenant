const LANGUAGE_NAMES = {
  de: 'German',
  en: 'English',
  es: 'Spanish',
  fr: 'French',
  hi: 'Hindi',
  it: 'Italian',
  ja: 'Japanese',
  nl: 'Dutch',
  pt: 'Portuguese',
};

function label(field) {
  return field ? `'${field}'` : 'The item';
}

function inField(field) {
  return field ? ` in '${field}'` : '';
}

function languageName(code) {
  return LANGUAGE_NAMES[code] ?? code;
}

/** One hard check, in the same words the Arbiter uses for it. */
export function checkSummary(check) {
  const params = check?.params ?? {};
  switch (check?.type) {
    case 'item_count_equals':
      return `All ${params.count} items present`;
    case 'json_schema_valid':
      return 'Valid JSON in the agreed format';
    case 'field_present':
      return `'${params.field}' filled in`;
    case 'field_unchanged':
      return `'${params.field}' unchanged from the source`;
    case 'language_is':
      return `${label(params.field)} written in ${languageName(params.language)}`;
    case 'no_source_language_left':
      return `No ${languageName(params.source_language)} left${inField(params.field)}`;
    case 'min_length':
      return `${label(params.field)} at least ${params.min} characters`;
    case 'max_length':
      return `${label(params.field)} at most ${params.max} characters`;
    case 'regex_match':
      return `${label(params.field)} matches ${params.pattern}`;
    case 'source_grounded':
      return `Numbers in ${label(params.field)} come from the source`;
    case 'file_type_in':
      return `Files are ${(params.types ?? []).join(', ')}`;
    case 'file_count_between':
      return `${params.min} to ${params.max} files`;
    case 'no_hidden_text':
      return 'No hidden text';
    default:
      return String(check?.type ?? 'Check').replaceAll('_', ' ');
  }
}

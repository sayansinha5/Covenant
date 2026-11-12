/**
 * Puts server validation errors on the matching form fields. `codeFields` maps a problem code
 * (e.g. EMAIL_TAKEN) to the field it belongs to. Returns true when anything was placed on a field;
 * otherwise the caller shows `problem.detail` as a form-level message.
 */
export function applyServerErrors(problem, setError, fields, codeFields = {}) {
  let placed = false;
  for (const { field, message } of problem.errors) {
    if (fields.includes(field)) {
      setError(field, { type: 'server', message });
      placed = true;
    }
  }
  const field = codeFields[problem.code];
  if (field) {
    setError(field, { type: 'server', message: problem.detail });
    placed = true;
  }
  return placed;
}

export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_LENGTH = 128;

/** Mirrors `password_problems` in the backend so the checklist and the server agree. */
export const PASSWORD_RULES = [
  {
    id: 'length',
    label: `At least ${PASSWORD_MIN_LENGTH} characters`,
    test: (v) => v.length >= PASSWORD_MIN_LENGTH,
  },
  { id: 'letter', label: 'One letter', test: (v) => /[A-Za-z]/.test(v) },
  { id: 'number', label: 'One number', test: (v) => /\d/.test(v) },
];

export function passwordMeetsRules(value) {
  return value.length <= PASSWORD_MAX_LENGTH && PASSWORD_RULES.every((rule) => rule.test(value));
}

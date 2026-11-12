import { useLayoutEffect, useState } from 'react';
import { createPortal } from 'react-dom';

/** Renders step buttons into the bar fixed at the bottom of the onboarding section. */
export function StepActions({ children }) {
  const [target, setTarget] = useState(null);

  useLayoutEffect(() => {
    setTarget(document.getElementById('onboarding-actions'));
  }, []);

  if (!target) return null;
  return createPortal(children, target);
}

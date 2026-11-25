import React, {useId, useState} from 'react';
import {projectDateError} from './projectDates.js';

export function useProjectDateFeedback(draft) {
  const [attempted, setAttempted] = useState(false);
  const issue = projectDateError(draft);
  function validateDates(form) {
    if (!issue) return true;
    setAttempted(true);
    form.elements.namedItem(issue.field)?.focus();
    return false;
  }
  return {dateIssue: attempted ? issue : null, validateDates};
}

export function ProjectDateField({field, label, value, issue, onChange}) {
  const id = useId();
  const message = issue?.field === field ? issue.message : null;
  return <div className="field project-date-field">
    <label htmlFor={id}>{label}</label>
    <input className={message ? 'input input-error' : 'input'} id={id} name={field} type="date"
      value={value ?? ''} aria-invalid={message ? true : undefined} aria-describedby={message ? id+'-error' : undefined}
      onChange={event => onChange(field, event.target.value)}/>
    {message && <p id={id+'-error'} className="error project-date-error" role="alert">{message}</p>}
  </div>;
}

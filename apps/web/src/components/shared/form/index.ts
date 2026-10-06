import { createFormHook } from "@tanstack/react-form";

import { fieldContext, formContext } from "./contexts";
import { ComboboxField, DateTimeField, SelectField, TextareaField, TextField } from "./fields";
import { SubmitButton } from "./submit-button";

/**
 * `useAppForm` is `useForm` with the field components in ./fields and the
 * submit button pre-bound, per the TanStack Form "form composition" guide.
 * Forms validate with a Zod schema passed as `validators.onDynamic` and
 * `validationLogic: revalidateLogic()`: quiet until the first submit, then
 * live on every change. Render them inside <Form>, which does the submit
 * wiring and the keyboard and focus behaviour every form should share.
 */
export const { useAppForm, withForm } = createFormHook({
  fieldContext,
  formContext,
  fieldComponents: { TextField, TextareaField, SelectField, ComboboxField, DateTimeField },
  formComponents: { SubmitButton },
});

export { Form, FormActions, FormSections, FormSection } from "./form";
export { FormError } from "./form-error";
export type { SelectOption } from "./fields";

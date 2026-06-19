import { forwardRef, memo, useEffect, useImperativeHandle, useRef } from 'react'

export interface PromptTextareaHandle {
  getValue: () => string
  setValue: (text: string) => void
  focus: () => void
}

interface PromptTextareaProps {
  initialValue: string
  onTextChange?: (text: string) => void
}

export const PromptTextarea = memo(
  forwardRef<PromptTextareaHandle, PromptTextareaProps>(function PromptTextarea(
    { initialValue, onTextChange },
    ref,
  ) {
    const textareaRef = useRef<HTMLTextAreaElement>(null)

    useImperativeHandle(ref, () => ({
      getValue: () => textareaRef.current?.value ?? '',
      setValue: (text: string) => {
        if (textareaRef.current) {
          textareaRef.current.value = text
          onTextChange?.(text)
        }
      },
      focus: () => textareaRef.current?.focus(),
    }))

    useEffect(() => {
      if (textareaRef.current && textareaRef.current.value !== initialValue) {
        textareaRef.current.value = initialValue
        onTextChange?.(initialValue)
      }
    }, [initialValue, onTextChange])

    return (
      <textarea
        ref={textareaRef}
        className="prompt-textarea"
        defaultValue={initialValue}
        onInput={event => onTextChange?.(event.currentTarget.value)}
        rows={4}
        required
        dir="ltr"
        lang="en"
        autoComplete="off"
        autoCorrect="on"
        spellCheck
        placeholder="Example: A dog running on a beach at sunset, cinematic wide shot, natural motion..."
      />
    )
  }),
)

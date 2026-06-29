import { useEffect, useId, useMemo, useRef, useState } from "react";

import type { Locale } from "../i18n/messages";

export type LocaleOption = {
  value: Locale;
  label: string;
};

type LanguagePickerProps = {
  label: string;
  value: Locale;
  options: LocaleOption[];
  onChange: (value: Locale) => void;
};

export function LanguagePicker({ label, value, options, onChange }: LanguagePickerProps) {
  const listboxId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(() => options.findIndex((option) => option.value === value));
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedOption = useMemo(
    () => options.find((option) => option.value === value) ?? options[0],
    [options, value],
  );

  useEffect(() => {
    setActiveIndex(options.findIndex((option) => option.value === value));
  }, [options, value]);

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (!isOpen) return;

      const target = event.target as Node;
      if (buttonRef.current?.contains(target)) return;
      if (optionRefs.current.some((optionRef) => optionRef?.contains(target))) return;
      setIsOpen(false);
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
        buttonRef.current?.focus();
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    optionRefs.current[activeIndex]?.focus();
  }, [activeIndex, isOpen]);

  const moveActiveIndex = (nextIndex: number) => {
    const normalizedIndex = (nextIndex + options.length) % options.length;
    setActiveIndex(normalizedIndex);
  };

  const openMenu = () => {
    setIsOpen(true);
    const currentIndex = options.findIndex((option) => option.value === value);
    setActiveIndex(currentIndex >= 0 ? currentIndex : 0);
  };

  const commitSelection = (nextValue: Locale) => {
    onChange(nextValue);
    setIsOpen(false);
    buttonRef.current?.focus();
  };

  return (
    <label className="language-picker">
      <span>{label}</span>
      <div className="language-picker-control">
        <button
          ref={buttonRef}
          type="button"
          className="language-picker-trigger"
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          aria-controls={listboxId}
          onClick={() => (isOpen ? setIsOpen(false) : openMenu())}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              if (!isOpen) {
                openMenu();
                return;
              }
              moveActiveIndex(activeIndex + 1);
            }

            if (event.key === "ArrowUp") {
              event.preventDefault();
              if (!isOpen) {
                openMenu();
                return;
              }
              moveActiveIndex(activeIndex - 1);
            }

            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              if (!isOpen) {
                openMenu();
                return;
              }

              if (options[activeIndex]) {
                commitSelection(options[activeIndex].value);
              }
            }

            if (event.key === "Escape") {
              event.preventDefault();
              setIsOpen(false);
            }
          }}
        >
          <span className="language-picker-trigger-label">{selectedOption?.label ?? value}</span>
          <span className="language-picker-trigger-caret" aria-hidden="true">
            ▾
          </span>
        </button>

        {isOpen ? (
          <div className="language-picker-menu" id={listboxId} role="listbox" aria-label={label}>
            {options.map((option, index) => (
              <button
                key={option.value}
                ref={(element) => {
                  optionRefs.current[index] = element;
                }}
                type="button"
                className={`language-picker-option ${option.value === value ? "is-selected" : ""}`}
                role="option"
                aria-selected={option.value === value}
                onClick={() => commitSelection(option.value)}
                onMouseEnter={() => setActiveIndex(index)}
                onFocus={() => setActiveIndex(index)}
                onKeyDown={(event) => {
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    moveActiveIndex(index + 1);
                  }

                  if (event.key === "ArrowUp") {
                    event.preventDefault();
                    moveActiveIndex(index - 1);
                  }

                  if (event.key === "Home") {
                    event.preventDefault();
                    setActiveIndex(0);
                  }

                  if (event.key === "End") {
                    event.preventDefault();
                    setActiveIndex(options.length - 1);
                  }

                  if (event.key === "Escape") {
                    event.preventDefault();
                    setIsOpen(false);
                    buttonRef.current?.focus();
                  }
                }}
              >
                <span className="language-picker-option-label">{option.label}</span>
                {option.value === value ? <span aria-hidden="true">✓</span> : null}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </label>
  );
}
// Design-system multi-select dropdown (GDM Lagoons Design System).
// Untitled UI "dropdown with search" pattern (untitledui.com/react/components/dropdowns)
// built on react-aria-components: trigger button -> anchored popover with a
// search field, checkbox option list (~20 rows per view, then scroll), and
// Select all / Clear footer. Fully keyboard navigable; Escape / outside click
// closes. Selection is drafted while open and applied once on close via
// onApply — one save per visit, not one per checkbox.
import React, { useState } from 'react'
import {
  Autocomplete,
  Button as AriaButton,
  Dialog,
  DialogTrigger,
  Input,
  ListBox,
  ListBoxItem,
  Popover,
  SearchField,
  useFilter,
  type Selection,
} from 'react-aria-components'
import { Check, ChevronDown, Search } from 'lucide-react'
import { COLORS, RADIUS, SHADOW } from '../../lib/tokens'

export interface MultiSelectOption {
  id: string
  label: string
}

export interface MultiSelectDropdownProps {
  /** Trigger button text (summary of the current selection). */
  label: string
  options: MultiSelectOption[]
  selectedIds: string[]
  /** Called once, when the popover closes with a changed selection. */
  onApply: (ids: string[]) => void
  disabled?: boolean
  /** Tooltip on the trigger button. */
  title?: string
  searchPlaceholder?: string
  emptyText?: string
  /** Rows visible before the list scrolls (default 20). */
  maxVisibleRows?: number
  triggerStyle?: React.CSSProperties
}

const ROW_HEIGHT = 34

export const MultiSelectDropdown: React.FC<MultiSelectDropdownProps> = ({
  label,
  options,
  selectedIds,
  onApply,
  disabled,
  title,
  searchPlaceholder = 'Search…',
  emptyText = 'No options.',
  maxVisibleRows = 20,
  triggerStyle,
}) => {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Set<string>>(new Set())
  const { contains } = useFilter({ sensitivity: 'base' })

  const handleOpenChange = (isOpen: boolean) => {
    if (isOpen) {
      setDraft(new Set(selectedIds))
    } else {
      const next = [...draft]
      const changed = next.length !== selectedIds.length || next.some(id => !selectedIds.includes(id))
      if (changed) onApply(next)
    }
    setOpen(isOpen)
  }

  const handleSelectionChange = (sel: Selection) => {
    setDraft(sel === 'all' ? new Set(options.map(o => o.id)) : new Set([...sel] as string[]))
  }

  return (
    <DialogTrigger isOpen={open} onOpenChange={handleOpenChange}>
      <AriaButton
        isDisabled={disabled}
        aria-label={title || label}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '3px 10px', border: '1px solid #CBD5E1', borderRadius: 6,
          fontSize: '0.8rem', fontFamily: 'inherit', fontWeight: 600,
          background: '#fff', color: disabled ? COLORS.slateLight : '#374151',
          cursor: disabled ? 'not-allowed' : 'pointer',
          maxWidth: 220, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          ...triggerStyle,
        }}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</span>
        <ChevronDown size={12} style={{ flexShrink: 0 }} />
      </AriaButton>

      {/* react-aria measures the space between the trigger and the viewport
          edge and sets a max-height on the popover (flipping above the trigger
          when there is more room there). The dialog fills that box; the option
          list is the only flexible row, so once it hits the viewable limit it
          scrolls internally and the search + footer stay pinned. */}
      <Popover
        placement="bottom start"
        offset={4}
        containerPadding={12}
        style={{
          background: '#fff',
          border: `1px solid ${COLORS.border}`,
          borderRadius: RADIUS.md,
          boxShadow: SHADOW.lg,
          width: 300,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Dialog
          aria-label={title || label}
          style={{ outline: 'none', display: 'flex', flexDirection: 'column', minHeight: 0, flex: 1 }}
        >
          <Autocomplete filter={contains}>
            {/* Search */}
            <SearchField
              aria-label={searchPlaceholder}
              autoFocus
              style={{
                display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
                borderBottom: `1px solid ${COLORS.border}`, padding: '10px 12px',
              }}
            >
              <Search size={14} color={COLORS.slate} style={{ flexShrink: 0 }} />
              <Input
                placeholder={searchPlaceholder}
                style={{
                  flex: 1, border: 'none', outline: 'none', fontSize: '0.85rem',
                  fontFamily: 'inherit', color: COLORS.ink, background: 'transparent',
                }}
              />
            </SearchField>

            {/* Options — checkbox rows, ~maxVisibleRows per view then scroll */}
            <ListBox
              selectionMode="multiple"
              selectedKeys={draft}
              onSelectionChange={handleSelectionChange}
              items={options}
              style={{
                // Cap at maxVisibleRows on tall screens; on short screens the
                // popover's viewport-derived max-height wins and this row
                // shrinks (flex + minHeight 0) and scrolls.
                overflowY: 'auto', maxHeight: ROW_HEIGHT * maxVisibleRows,
                flex: '1 1 auto', minHeight: 0,
                padding: '6px 6px', outline: 'none',
              }}
              renderEmptyState={() => (
                <div style={{ padding: '1rem', fontSize: '0.85rem', color: COLORS.slateLight, textAlign: 'center' }}>
                  {emptyText}
                </div>
              )}
            >
              {(o: MultiSelectOption) => (
                <ListBoxItem
                  id={o.id}
                  textValue={o.label}
                  style={({ isFocused }) => ({
                    display: 'flex', alignItems: 'flex-start', gap: 10,
                    padding: '7px 8px', borderRadius: 6, cursor: 'pointer',
                    fontSize: '0.85rem', color: '#374151', lineHeight: 1.4,
                    minHeight: ROW_HEIGHT - 8, outline: 'none',
                    background: isFocused ? COLORS.surface : 'transparent',
                  })}
                >
                  {({ isSelected }) => (
                    <>
                      <span
                        aria-hidden
                        style={{
                          width: 16, height: 16, borderRadius: 4, flexShrink: 0, marginTop: 1,
                          border: `1.5px solid ${isSelected ? COLORS.accent : '#CBD5E1'}`,
                          background: isSelected ? COLORS.accent : '#fff',
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          transition: 'background 0.1s, border-color 0.1s',
                        }}
                      >
                        {isSelected && <Check size={12} color="#fff" strokeWidth={3} />}
                      </span>
                      <span style={{ overflowWrap: 'anywhere' }}>{o.label}</span>
                    </>
                  )}
                </ListBoxItem>
              )}
            </ListBox>
          </Autocomplete>

          {/* Footer — bulk actions + live count; closing applies the draft */}
          <div
            style={{
              display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
              borderTop: `1px solid ${COLORS.border}`, padding: '10px 12px',
            }}
          >
            <button
              type="button"
              onClick={() => setDraft(new Set(options.map(o => o.id)))}
              style={{ background: '#fff', color: '#374151', border: '1px solid #CBD5E1', borderRadius: 6, padding: '4px 10px', fontSize: '0.75rem', fontWeight: 600, fontFamily: 'inherit', cursor: 'pointer' }}
            >
              Select all
            </button>
            <button
              type="button"
              onClick={() => setDraft(new Set())}
              style={{ background: '#fff', color: '#374151', border: '1px solid #CBD5E1', borderRadius: 6, padding: '4px 10px', fontSize: '0.75rem', fontWeight: 600, fontFamily: 'inherit', cursor: 'pointer' }}
            >
              Clear
            </button>
            <span style={{ flex: 1, textAlign: 'right', fontSize: '0.75rem', color: COLORS.slate }}>
              {draft.size} of {options.length}
            </span>
            <button
              type="button"
              onClick={() => handleOpenChange(false)}
              style={{ background: COLORS.accent, color: '#fff', border: 'none', borderRadius: 6, padding: '4px 12px', fontSize: '0.75rem', fontWeight: 600, fontFamily: 'inherit', cursor: 'pointer' }}
            >
              Done
            </button>
          </div>
        </Dialog>
      </Popover>
    </DialogTrigger>
  )
}

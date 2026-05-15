export interface DropdownItem {
  text?: string
  icon?: any
  shortcut?: string
  danger?: boolean
  disabled?: boolean
  onClick?: () => void
  divider?: boolean
  label?: string
}

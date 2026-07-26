import type { Component } from 'vue'

export interface DropdownItem {
  text?: string
  icon?: Component
  shortcut?: string
  danger?: boolean
  disabled?: boolean
  onClick?: () => void
  divider?: boolean
  label?: string
}

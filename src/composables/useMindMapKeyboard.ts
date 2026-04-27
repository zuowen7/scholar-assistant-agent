import { useMindMap, undo, redo } from './useMindMap'

export function useMindMapKeyboard() {
  const {
    selectedNodeId, selectedNode, draftMindMap,
    addChild, addSibling, selectNode,
  } = useMindMap()

  function isEditing(e: KeyboardEvent): boolean {
    const t = e.target as HTMLElement
    return t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable
  }

  function focusNodeAndEdit(id: string) {
    selectNode(id)
    requestAnimationFrame(() => {
      const nodeEl = document.querySelector(`[data-id="${id}"]`)
      if (!nodeEl) return
      const textEl = nodeEl.querySelector('.node-text') as HTMLElement
      textEl?.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))
    })
  }

  function onKeydown(e: KeyboardEvent) {
    if (isEditing(e)) return

    const id = selectedNodeId.value
    const node = selectedNode.value
    if (!id || !node) return

    if (e.key === 'Tab') {
      e.preventDefault()
      const newId = addChild(id)
      if (newId) focusNodeAndEdit(newId)
      return
    }

    if (e.key === 'Enter') {
      e.preventDefault()
      const newId = node.parentId ? addSibling(id) : addChild(id)
      if (newId) focusNodeAndEdit(newId)
      return
    }

    if (e.key === 'F2') {
      e.preventDefault()
      focusNodeAndEdit(id)
      return
    }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
      e.preventDefault()
      e.shiftKey ? redo() : undo()
      return
    }

    if (e.key === 'ArrowUp' || e.key === 'ArrowDown' ||
        e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault()
      moveSelection(e.key)
    }
  }

  function moveSelection(key: string) {
    const node = selectedNode.value
    if (!node) return
    const map = draftMindMap.value

    if (key === 'ArrowRight' && node.children.length) {
      selectNode(node.children[0])
    } else if (key === 'ArrowLeft' && node.parentId) {
      selectNode(node.parentId)
    } else if ((key === 'ArrowUp' || key === 'ArrowDown') && node.parentId) {
      const siblings = map.nodes[node.parentId].children
      const idx = siblings.indexOf(node.id)
      const next = key === 'ArrowUp' ? idx - 1 : idx + 1
      if (next >= 0 && next < siblings.length) selectNode(siblings[next])
    }
  }

  return { onKeydown }
}

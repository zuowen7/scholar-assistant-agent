interface InlineDiffZone {
  afterLineNumber: number
  heightInPx: number
  domNode: HTMLElement
}

interface InlineDiffZoneAccessor {
  addZone(zone: InlineDiffZone): string
  removeZone(id: string): void
}

export interface InlineDiffZoneEditor {
  changeViewZones(callback: (accessor: InlineDiffZoneAccessor) => void): void
}

export interface InlineDiffViewOptions {
  afterLineNumber: number
  newText: string
  title: string
  acceptLabel: string
  rejectLabel: string
  onAccept: () => void
  onReject: () => void
}

export interface InlineDiffViewHandle {
  id: string
  remove: () => void
}

const VIEW_ZONE_HEIGHT = 280

function button(label: string, className: string, onClick: () => void): HTMLButtonElement {
  const element = document.createElement('button')
  element.type = 'button'
  element.className = className
  element.textContent = label
  element.addEventListener('click', onClick)
  return element
}

/** Add a Copilot-style inline diff that reserves editor space instead of covering text. */
export function addInlineDiffViewZone(
  editor: InlineDiffZoneEditor,
  options: InlineDiffViewOptions,
): InlineDiffViewHandle {
  const zone = document.createElement('div')
  zone.className = 'ai-diff-zone'
  zone.addEventListener('mousedown', (event) => event.stopPropagation())

  const card = document.createElement('section')
  card.className = 'ai-diff-card'
  card.setAttribute('aria-label', options.title)

  const header = document.createElement('header')
  header.className = 'ai-diff-header'

  const title = document.createElement('span')
  title.className = 'ai-diff-title'
  title.textContent = options.title
  header.append(title)

  const content = document.createElement('div')
  content.className = 'ai-diff-new ai-diff-scroll'
  content.textContent = options.newText

  const actions = document.createElement('footer')
  actions.className = 'ai-diff-actions'
  actions.append(
    button(options.acceptLabel, 'ai-diff-accept', options.onAccept),
    button(options.rejectLabel, 'ai-diff-reject', options.onReject),
  )

  card.append(header, content, actions)
  zone.append(card)

  let id = ''
  editor.changeViewZones((accessor) => {
    id = accessor.addZone({
      afterLineNumber: options.afterLineNumber,
      heightInPx: VIEW_ZONE_HEIGHT,
      domNode: zone,
    })
  })

  return {
    id,
    remove: () => {
      if (!id) return
      editor.changeViewZones((accessor) => accessor.removeZone(id))
      id = ''
    },
  }
}

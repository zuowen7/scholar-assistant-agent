/// <reference types="vite/client" />

declare module '*?worker' {
  const workerConstructor: new () => Worker
  export default workerConstructor
}

// View Transition API (not yet in lib.dom.d.ts)
interface ViewTransition {
  ready: Promise<void>
  finished: Promise<void>
  updateCallbackDone: Promise<void>
  skipTransition(): void
}

interface Document {
  startViewTransition(callback: () => void | Promise<void>): ViewTransition
}

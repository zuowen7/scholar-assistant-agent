/**
 * IndexedDB persistence for translation results.
 * Stores completed translations so they can be recovered after page refresh.
 */

const DB_NAME = 'scholar-assistant'
const DB_VERSION = 1
const STORE_NAME = 'translations'

interface PersistedTranslation {
  id: string
  savedAt?: number
  finalContent: string
  blocks: unknown[]
  chunks: { original: string; translated: string }[]
  parsedInfo: unknown
  stepMessage: string
  fallbackChunks: number
  misalignedChunks: number
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export async function persistTranslation(data: PersistedTranslation): Promise<void> {
  try {
    const db = await openDB()
    const tx = db.transaction(STORE_NAME, 'readwrite')
    const store = tx.objectStore(STORE_NAME)
    store.put({ ...data, savedAt: Date.now() })
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
    db.close()
  } catch {
    // IndexedDB unavailable — silent fail
  }
}

export async function loadLastTranslation(): Promise<PersistedTranslation | null> {
  try {
    const db = await openDB()
    const tx = db.transaction(STORE_NAME, 'readonly')
    const store = tx.objectStore(STORE_NAME)
    const req = store.getAll()
    const result = await new Promise<PersistedTranslation[]>((resolve, reject) => {
      req.onsuccess = () => resolve(req.result as PersistedTranslation[])
      req.onerror = () => reject(req.error)
    })
    db.close()
    if (result.length === 0) return null
    // Return most recent
    result.sort((a, b) => (b.savedAt ?? 0) - (a.savedAt ?? 0))
    return result[0]
  } catch {
    return null
  }
}

export async function clearPersistedTranslation(id: string): Promise<void> {
  try {
    const db = await openDB()
    const tx = db.transaction(STORE_NAME, 'readwrite')
    tx.objectStore(STORE_NAME).delete(id)
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
    db.close()
  } catch {
    // silent
  }
}
